"""Run bounded existing worker tests with exit diagnostics; edits no engine files.

Example on a Windows checkout:
  python stud-windows-worker-diagnostic.py --engine . --output probe-direct --mode direct
  python stud-windows-worker-diagnostic.py --engine . --output probe-normal --mode normal
  python stud-windows-worker-diagnostic.py --engine . --output probe-fast --mode fast

Direct preserves each original worker entrypoint. Normal and fast wrap run() to
mark its return; fast exits immediately AFTER run returned its real status.
Use fast only to diagnose shutdown, never to reinterpret an unobserved failure.
"""
import argparse
import atexit
import faulthandler
import gc
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import threading
import unittest
import uuid

DEFAULT_TESTS = [
    'test_session.EvaluationAndFinishTests.test_real_builds_have_distinct_ids_and_independent_geometry_evidence',
    'test_native_operations.NativeOperationsTests.test_native_measurement_names_picks_and_stale_sources',
    'test_native_operations.NativeOperationsTests.test_pdf_scale_immutable_export_retry_and_source_mismatch',
]


def marker(phase, **details):
    print('[STUD-PROBE] '+json.dumps(dict(phase=phase, **details)), file=sys.stderr, flush=True)


def child():
    parser=argparse.ArgumentParser()
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--mode', choices=['normal','fast'], required=True)
    parser.add_argument('--collect', action='store_true')
    args=parser.parse_args()
    faulthandler.enable(all_threads=True)
    atexit.register(marker, 'atexit_marker')
    marker('before_import', worker=str(args.worker))
    namespace=runpy.run_path(str(args.worker), run_name='stud_probe_worker')
    marker('before_run')
    code=namespace['run'](json.loads(args.input.read_bytes()))
    marker('run_returned', status=code)
    if args.collect:
        marker('before_gc')
        collected=gc.collect()
        marker('after_gc', collected=collected)
    marker('before_exit', mode=args.mode, status=code)
    sys.stdout.flush()
    sys.stderr.flush()
    if args.mode=='fast':
        os._exit(code)
    return code


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['direct','normal','fast'], default='direct')
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--tests', nargs='+', default=DEFAULT_TESTS)
    args=parser.parse_args()
    if not 1 <= args.repeat <= 10:
        parser.error('--repeat must be between 1 and 10')
    if args.collect and args.mode=='direct':
        parser.error('--collect requires a wrapped mode')
    engine=args.engine.resolve()
    destination=args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    probe=Path(__file__).resolve()
    sys.path[:0]=[str(engine), str(engine/'tests')]
    original=subprocess.Popen
    lock=threading.Lock()

    class ObservedPopen(original):
        def __init__(self, command, *positional, **kwargs):
            self.probe_info=None
            self.probe_recorded=False
            if isinstance(command, (list,tuple)):
                command=list(command)
                for index, part in enumerate(command):
                    if Path(str(part)).name not in ('worker.py','native_worker.py'):
                        continue
                    worker=Path(part).resolve()
                    flag='--job' if worker.name=='worker.py' else '--request'
                    input_path=Path(command[command.index(flag)+1]).resolve()
                    payload=json.loads(input_path.read_bytes())
                    directory=Path(payload['artifact_path']) if flag=='--job' else Path(payload['result_path']).parent
                    self.probe_info=(worker,input_path,directory)
                    prefix=command[:index]+['-X','faulthandler']
                    if args.mode=='direct':
                        command=prefix+command[index:]
                    else:
                        command=prefix+[str(probe),'--child','--worker',str(worker),'--input',str(input_path),'--mode',args.mode]
                        if args.collect:
                            command.append('--collect')
                    break
            super().__init__(command, *positional, **kwargs)

        def wait(self, *positional, **kwargs):
            code=super().wait(*positional, **kwargs)
            if self.probe_info:
                with lock:
                    if not self.probe_recorded:
                        self.probe_recorded=True
                        worker,input_path,directory=self.probe_info
                        retained=destination/f'{worker.stem}-{self.pid}-{uuid.uuid4().hex[:8]}'
                        retained.mkdir()
                        summary=dict(worker=worker.name, mode=args.mode, pid=self.pid,
                                     exit_code=code, exit_u32_hex=f'0x{code & 0xffffffff:08X}', directory=str(retained))
                        try:
                            shutil.copy2(input_path, retained/'input.json')
                            for name in ('stderr.log','manifest.json','geometry.json','partial.json','result.json'):
                                artifact=directory/name
                                if artifact.is_file():
                                    shutil.copy2(artifact, retained/name)
                                    if name.endswith('.json'):
                                        value=json.loads(artifact.read_bytes())
                                        summary[name]={k:value[k] for k in ('artifact_stage','completion','diagnostics','status','error') if k in value}
                            (retained/'exit.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
                            marker('process_exit', **summary)
                            if code and (retained/'stderr.log').is_file():
                                print((retained/'stderr.log').read_bytes().decode('utf-8',errors='replace')[-16000:], file=sys.stderr, flush=True)
                        except Exception as error:
                            marker('capture_failed', error=repr(error), **summary)
            return code

    subprocess.Popen=ObservedPopen
    try:
        suite=unittest.TestSuite()
        for _ in range(args.repeat):
            suite.addTests(unittest.defaultTestLoader.loadTestsFromNames(args.tests))
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    finally:
        subprocess.Popen=original


if __name__=='__main__':
    raise SystemExit(child() if '--child' in sys.argv else main())
