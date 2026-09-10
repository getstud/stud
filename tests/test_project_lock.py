"""Live project copying must coexist with single-coordinator exclusion."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from stud.contracts import ProjectLock


class ProjectLockTests(unittest.TestCase):
    def test_copy_locked_project_preserves_exclusion_and_releases_on_close(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'project';root.mkdir()
            lock_path=root/'coordinator.lock'
            # Include the one-byte marker written by the previous Windows code.
            lock_path.write_bytes(b'\0')
            (root/'design.py').write_text('preserved design\n')
            with ProjectLock(lock_path):
                copied=Path(temporary)/'copy'
                shutil.copytree(root,copied)
                self.assertEqual((copied/'design.py').read_bytes(),(root/'design.py').read_bytes())
                result=subprocess.run([sys.executable,'-c',
                    'import sys\nfrom stud.contracts import ProjectLock,StudError\n'
                    'try:\n lock=ProjectLock(sys.argv[1])\n'
                    'except StudError as error:\n print(error.category)\n'
                    'else:\n lock.close();raise SystemExit(2)\n',str(lock_path)],
                    capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout.strip(),'coordinator_busy')
                # The copied lock belongs to a different project folder.
                with ProjectLock(copied/'coordinator.lock'):pass
            with ProjectLock(lock_path):pass
