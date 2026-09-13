"""Disposable memoized native evidence, keyed by exact geometric inputs."""
from copy import deepcopy

from .contracts import StudError, digest, read_json, write_json


class QueryCache:
    def __init__(self,path=None):
        self.path=path
        self.entries={}
        self.dirty=False
        if path:
            try:
                saved=read_json(path,{})
                if isinstance(saved,dict) and saved.get('schema_version')==1 and isinstance(saved.get('entries'),dict) and digest(saved['entries'])==saved['sha256']:
                    self.entries=saved['entries']
            except (OSError,ValueError,KeyError,TypeError):pass

    def key(self,model,requirement):
        kind=requirement['kind']
        if kind not in ('stock_fit','contact','support','clearance','distance','collision','panel_edge_support','panel_edge_system','solid_valid','collision_free'):
            return None
        targets=requirement['targets']
        if any(target not in model.objects or target not in model.shapes for target in targets):return None
        shapes=[]
        for target in targets:
            obj=model.objects[target]
            if kind=='stock_fit':
                # This operation is entirely in the registered local stock
                # frame. Equal native bytes and blanks also share evidence
                # between separate instances within one full evaluation.
                shapes.append(dict(shape=obj['shape_digest'],blank=obj.get('blank')))
            else:
                shapes.append(dict(id=target,shape=obj['shape_digest'],placement=obj['placement'],
                    factory_edges=(obj.get('blank') or {}).get('factory_edges',[]) if kind=='panel_edge_system' else None))
        try:
            return digest(dict(schema_version=1,units=model.units,declared_units=requirement.get('units'),kind=kind,shapes=shapes,
                threshold=requirement['threshold'],tolerance=requirement['tolerance'],policy=requirement.get('policy',{})))
        except (TypeError,ValueError):return None

    def get(self,key):
        return deepcopy(self.entries[key]) if key in self.entries else None

    def put(self,key,result):
        if key is None:return
        self.entries[key]=deepcopy(result);self.dirty=True

    def save(self):
        if not self.path or not self.dirty:return
        # A lost concurrent cache update can only cause a later cache miss.
        # Saved project evidence and current calculations never depend on it.
        try:
            while len(self.entries)>50000:self.entries.pop(next(iter(self.entries)))
            write_json(self.path,dict(schema_version=1,entries=self.entries,sha256=digest(self.entries)))
        except (OSError,StudError):pass
