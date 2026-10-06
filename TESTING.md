# Running tests

Open a terminal in the project root (`MS-Strats-PTurini`).

Run all tests:

```powershell
python -m unittest discover -s tests -v
```

Run only the model tests:

```powershell
python -m unittest discover -s tests -p "test_models.py" -v
```

`OK` means all tests passed. `-v` shows each test's name and result.

Use these commands in the VS Code terminal. Running `tests/test_models.py` directly with Code Runner can cause `ModuleNotFoundError` because Python cannot find `MatchingEngine` from the test directory.
