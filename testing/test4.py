from subprocess import Popen
from subprocess import STDOUT
from subprocess import PIPE

try:
    proc = Popen("", cwd=cwd, stdout=PIPE, stderr=STDOUT)
    out, err = proc.communicate(timeout=5)
    returncode = proc.returncode
except Exception:
    proc.kill()