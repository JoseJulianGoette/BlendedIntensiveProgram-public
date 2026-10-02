OCR example scripts
===================

Install Python first
--------------------

0. Install 64-bit Python before creating the virtual environment.

   For Windows, download the Python 3.11 installer from:

   https://www.python.org/downloads/windows/

   In the installer, enable "Add python.exe to PATH". Complete the installation,
   close PowerShell, and open a new terminal. Then check the installation:

   python --version
   python -c "import platform; print(platform.architecture()[0])"

   The expected output is Python 3.11.x and ``64bit``.

   Current PaddlePaddle documentation supports Python 3.9 through 3.13. This
   course pins PaddlePaddle 3.2.0. Its Windows wheels are available for Python
   3.9, 3.10, 3.11, and 3.12. Python 3.11 is the recommended course version.

   If ``python`` opens the Microsoft Store or is not recognized, disable the
   Windows App Installer aliases for python.exe and python3.exe, then reopen
   PowerShell.

PaddleOCR environment
---------------------

1. Create a virtual environment for PaddleOCR. On Windows, use a short path
   because PaddlePaddle contains deeply nested files:

   python -m venv C:\venvs\paddleocr

   Check ``python --version`` first. The course examples use Python 3.11. The
   optional ``py`` launcher is not available on every Windows installation.

2. Activate the environment in PowerShell:

   C:\venvs\paddleocr\Scripts\Activate.ps1

   The prompt should now begin with ``(paddleocr)``. Confirm the active Python:

   python -c "import sys; print(sys.executable)"
   python -m pip --version

   Both paths must point into C:\venvs\paddleocr. If PowerShell blocks the
   activation script, allow it only for the current terminal and try again:

   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   C:\venvs\paddleocr\Scripts\Activate.ps1

3. Open PowerShell in this directory and install the dependencies:

   python -m pip install --upgrade pip setuptools wheel
   python -m pip install -r requirements.txt

   The course uses plain ``paddleocr`` rather than ``paddleocr[all]`` because
   it does not require every optional document-processing dependency.

4. Run the examples in order:

   python 01_paddleocr_basic.py
   python 02_paddleocr_export.py
   python 03_paddleocr_evidence.py

   Step 1 runs OCR and prints PaddleOCR's raw result.
   Step 2 exports the raw JSON result and a visualization to ``paddle_output``.
   Step 3 creates ``paddle_evidence.json`` with text, confidence, and original
   polygon coordinates.

   The first run may download OCR model files. All scripts locate the included
   synthetic ``example.png`` relative to their own file location. They also
   work when started from the repository root, for example:

   python deliverables/ocr_examples/01_paddleocr_basic.py

5. Leave the environment when finished:

   deactivate

   This does not delete the environment. Activate it again in the next session
   with C:\venvs\paddleocr\Scripts\Activate.ps1.

VS Code
-------

Use "Python: Select Interpreter" and select:

   C:\venvs\paddleocr\Scripts\python.exe

Open a new VS Code terminal after changing the interpreter.

Archived examples
-----------------

The earlier Tesseract scripts and their requirements file are retained in the
``old`` directory. They are not part of the current student exercise.

Outputs
-------

01 prints the raw PaddleOCR result.
02 writes raw JSON and visualization files under ``paddle_output``.
03 writes normalized evidence to ``paddle_evidence.json``.
