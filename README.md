# Epicboxie

Forked from [StepicOrg/epicbox](https://github.com/StepicOrg/) for some improvements.

This fork allows to expose container ports with host machine and to work with sandbox interactively.

`epicboxie.run_interactive` is a context manager that runs sandbox:

```python
import time
import requests
import epicboxie

epicboxie.configure(
    profiles=[
        epicboxie.Profile('python', 'python:3.6.5-alpine')
    ]
)

with open('server.py', 'rb') as f:
    contents = f.read()
files = [{'name': 'main.py', 'content': contents}]
limits = {'cputime': 1, 'memory': 64}
ports = {8000: 8000}

with epicboxie.run_interactive('python', 'python3 main.py', files=files, limits=limits, ports=ports) as run:
    time.sleep(2)
    print(requests.get('http://localhost:8000').status_code)

result = run.results
```

The `ports` parameter is also added to old `run` function.

Interaction with standard I/O is done with `run.docker_interaction.read_sock()` and `run.docker_interaction.write_sock()`:

```python
import time
import requests
import epicboxie

epicboxie.configure(
    profiles=[
        epicboxie.Profile('python', 'python:3.6.5-alpine')
    ]
)
files = [{'name': 'main.py', 'content': b'print(input("Input data: ")[::-1])'}]
limits = {'cputime': 1, 'memory': 64}
ports = {8000: 8000}

with epicboxie.run_interactive('python', 'python3 main.py', files=files, limits=limits, ports=ports) as run:
    time.sleep(0.5)
    prompt = run.docker_interaction.read_sock()[0].decode('utf8')  # read_sock returns tuple (stdout, stderr)
    run.docker_interaction.write_sock(input(prompt).encode())
    time.sleep(0.5)
    print(run.docker_interaction.read_sock()[0].decode('utf8'))

result = run.results
```

If you need to use old-style automatic interaction (pass whole stdin and wait for termination) when using `run_interactive`, you can use `run.docker_interaction.interact(stdin, timeout, close=True)`

# Original README.md:
# epicbox
[![Build Status](https://travis-ci.org/PashaWNN/epicbox.svg?branch=master)](https://travis-ci.org/PashaWNN/epicbox)

A Python library to run untrusted code in secure, isolated [Docker](https://www.docker.com/)
based sandboxes. It is used to automatically grade programming assignments
on [Stepik.org](https://stepik.org/).

It allows to spawn a process inside one-time Docker container, send data
to stdin, and obtain its exit code and stdout/stderr output.  It's very similar
to what the [`subprocess`](https://docs.python.org/3/library/subprocess.html#module-subprocess)
module does but additionally you can specify a custom environment for the process
(a Docker [image](https://docs.docker.com/v17.09/engine/userguide/storagedriver/imagesandcontainers/))
and limit the CPU, memory, disk, and network usage for the running process.

## Usage
Run a simple Python script in a one-time Docker container using the
[`python:3.6.5-alpine`](https://hub.docker.com/_/python/) image:
```python
import epicboxie

epicboxie.configure(
    profiles=[
        epicboxie.Profile('python', 'python:3.6.5-alpine')
    ]
)
files = [{'name': 'main.py', 'content': b'print(42)'}]
limits = {'cputime': 1, 'memory': 64}
result = epicbox.run('python', 'python3 main.py', files=files, limits=limits)

```
The `result` value is:
```python
{'exit_code': 0,
 'stdout': b'42\n',
 'stderr': b'',
 'duration': 0.143358,
 'timeout': False,
 'oom_killed': False}
```

### Available Limit Options

The available limit options and default values:

```
DEFAULT_LIMITS = {
    # CPU time in seconds, None for unlimited
    'cputime': 1,
    # Real time in seconds, None for unlimited
    'realtime': 5,
    # Memory in megabytes, None for unlimited
    'memory': 64,

    # limit the max processes the sandbox can have
    # -1 or None for unlimited(default)
    'processes': -1,
}
```

### Advanced usage
A more advanced usage example of `epicbox` is to compile a C++ program and then
run it multiple times on different input data.  In this example `epicbox` will
run containers on a dedicated [Docker Swarm](https://docs.docker.com/swarm/overview/)
cluster instead of locally installed Docker engine:
```python
import epicboxie

PROFILES = {
    'gcc_compile': {
        'docker_image': 'stepik/epicboxie-gcc:6.3.0',
        'user': 'root',
    },
    'gcc_run': {
        'docker_image': 'stepik/epicboxie-gcc:6.3.0',
        # It's safer to run untrusted code as a non-root user (even in a container)
        'user': 'sandbox',
        'read_only': True,
        'network_disabled': False,
    },
}
epicboxie.configure(profiles=PROFILES, docker_url='tcp://1.2.3.4:2375')

untrusted_code = b"""
// C++ program
#include <iostream>

int main() {
    int a, b;
    std::cin >> a >> b;
    std::cout << a + b << std::endl;
}
"""
# A working directory allows to preserve files created in a one-time container
# and access them from another one. Internally it is a temporary Docker volume.
with epicboxie.working_directory() as workdir:
    epicboxie.run('gcc_compile', 'g++ -pipe -O2 -static -o main main.cpp',
                files=[{'name': 'main.cpp', 'content': untrusted_code}],
                workdir=workdir)
    epicboxie.run('gcc_run', './main', stdin='2 2',
                limits={'cputime': 1, 'memory': 64},
                workdir=workdir)
    # {'exit_code': 0, 'stdout': b'4\n', 'stderr': b'', 'duration': 0.095318, 'timeout': False, 'oom_killed': False}
    epicboxie.run('gcc_run', './main', stdin='14 5',
                limits={'cputime': 1, 'memory': 64},
                workdir=workdir)
    # {'exit_code': 0, 'stdout': b'19\n', 'stderr': b'', 'duration': 0.10285, 'timeout': False, 'oom_killed': False}
```

## Installation
`epicbox` can be installed by running `pip install epicbox`. It's tested on Python 3.4+ and
Docker 1.12+.

You can also check the [epicbox-images](https://github.com/StepicOrg/epicbox-images)
repository that contains Docker images used to automatically grade programming
assignments on [Stepik.org](https://stepik.org/).

## Contributing
Contributions are welcome, and they are greatly appreciated!
More details can be found in [CONTRIBUTING](CONTRIBUTING.rst).
