"""Publish immutable coherent previews while coalescing rapid registrations."""
from copy import deepcopy
import threading
import time


class GeometryPreview:
    """Freeze registered geometry without repeatedly copying the entire design.

    Objects and assets are immutable registrations; replacements arrive as new
    explicit entries. Quantities, requirements and construction instructions
    are published together at the complete geometry stage. Partial previews
    retain geometry and named measurement references, with those other stages
    explicitly pending.
    """
    def __init__(self):
        self.objects={};self.assets={};self.assemblies={}

    def freeze(self,model,changes):
        for change in changes:
            obj=deepcopy(change['object'])
            self.objects[obj['id']]=obj
            asset=change['asset']
            if asset['key'] not in self.assets:self.assets[asset['key']]=deepcopy(asset)
        self.objects={key:obj for key,obj in self.objects.items() if key in model.objects}
        for key,assembly in model.assemblies.items():
            if key not in self.assemblies:self.assemblies[key]=deepcopy({k:v for k,v in assembly.items() if not k.startswith('_')})
        return dict(name=model.name,units=model.units,preview_scope='geometry',objects=list(self.objects.values()),
            assets=dict(self.assets),assemblies=[obj for key,obj in self.assemblies.items() if key in model.assemblies],
            references=deepcopy(model.references),dimensions=deepcopy(list(model.dimensions.values())),
            requirements=[],demands=[],drawings=[],steps=[],connections=[],notes=list(model.notes),timings={})


def merge_changes(previous,entries):
    for entry in entries:
        key=entry['object']['id']
        if previous.get(key,{}).get('operation')=='add' and entry['operation']=='replace':
            entry={**entry,'operation':'add'}
        previous[key]=entry
    return previous


class PreviewPublisher:
    """One synchronous first frame, then a bounded queue containing the latest.

    The producer freezes metadata at a completed batch boundary. The writer
    never reads the mutable Model or any OCCT shapes. A slow writer can hold
    only its current snapshot and one newer snapshot; skipped notifications
    are folded into that next coherent snapshot.
    """
    def __init__(self, write, interval=None):
        self.write=write
        self.interval=interval or (lambda snapshot: .15 if len(snapshot.get('objects',[]))<512 else 1.0)
        self.condition=threading.Condition()
        self.pending=None
        self.thread=None
        self.closed=False
        self.error=None
        self.last_write=0.0
        self.timings=dict(snapshot_seconds=0.0,write_seconds=0.0,published=0,coalesced=0)

    def _write(self,snapshot,changes):
        started=time.perf_counter()
        self.write(snapshot,list(changes.values()))
        self.last_write=time.monotonic()
        self.timings['write_seconds']+=time.perf_counter()-started
        self.timings['published']+=1

    def submit(self,snapshot,changes, *, frozen=False):
        if self.error:raise self.error
        if self.closed:raise RuntimeError('The preview publisher has closed.')
        started=time.perf_counter()
        if not frozen:snapshot=deepcopy(snapshot)
        changes=merge_changes({},deepcopy(changes))
        self.timings['snapshot_seconds']+=time.perf_counter()-started
        if self.thread is None:
            self._write(snapshot,changes)
            self.thread=threading.Thread(target=self._run,name='stud-preview',daemon=True)
            self.thread.start()
            return
        with self.condition:
            if self.pending:
                previous=self.pending[1]
                merge_changes(previous,changes.values())
                changes=previous
                self.timings['coalesced']+=1
            self.pending=(snapshot,changes)
            self.condition.notify()

    def _run(self):
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(lambda:self.pending is not None or self.closed)
                    if self.pending is None:return
                    delay=self.last_write+self.interval(self.pending[0])-time.monotonic()
                    if delay>0 and not self.closed:
                        self.condition.wait(timeout=delay)
                        continue
                    snapshot,changes=self.pending
                    self.pending=None
                self._write(snapshot,changes)
        except BaseException as error:
            with self.condition:
                self.error=error
                self.pending=None
                self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closed=True
            self.condition.notify_all()
        if self.thread:self.thread.join()
        if self.error:raise self.error
