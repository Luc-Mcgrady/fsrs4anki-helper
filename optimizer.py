from .utils import *

from anki.exporting import AnkiPackageExporter
from anki.decks import DeckManager
from aqt.qt import QProcess
from aqt.utils import showInfo, showCritical

import os
import shutil
import sys
import json

class ExclusiveWorker:
    """Used to ensure that 2 tasks dont run at once"""
    process = QProcess()
    working = False
    message = ""

    def work(self, args=[], on_complete=lambda:None, message="Something is processing"):
        if not self.working:
            
            def wrapper():
                on_complete()
                self.process.finished.disconnect()
                self.working = False

            self.message = message
            self.process.start(args[0], args[1:])
            self.process.finished.connect(wrapper)
            self.working = True

            tooltip(self.message)
        else:
            tooltip(f"Waiting for '{self.message}' to complete")

_worker = ExclusiveWorker()

def optimize(did: int):
    global _worker

    try:
        from fsrs4anki_optimizer import Optimizer # only used as a check to see if its installed
    except ImportError:
        showCritical(
"""
You need to have the optimizer installed in order to optimize your decks using this option.
Please run Tools>FSRS4Anki helper>Install local optimizer.
Alternatively, use a different method of optimizing (https://github.com/open-spaced-repetition/fsrs4anki/releases)
""")
        return

    exporter = AnkiPackageExporter(mw.col)
    manager = DeckManager(mw.col)
    deck = manager.get(did)
    assert deck
    name = deck["name"]

    dir_path = os.path.expanduser("~/.fsrs4ankiHelper")
    tmp_dir_path = f"{dir_path}/tmp"

    exporter.did = did
    exporter.includeMedia = False
    exporter.includeSched = True

    filepath = f"{tmp_dir_path}/{did}.apkg"
    
    if not os.path.isdir(dir_path):
        os.mkdir(dir_path)
    if not os.path.isdir(tmp_dir_path):
        os.mkdir(tmp_dir_path)

    exporter.exportInto(filepath) 

    preferences = mw.col.get_preferences()

    timezone = "Europe/London" # todo: Automate this

    revlog_start_date = "2000-01-01" # todo: implement this

    # This is a workaround to the fact that module doesn't take these as arguments
    remembered_fallbacks = { 
        "timezone": timezone, 
        "next_day": preferences.scheduling.rollover,
        "revlog_start_date": revlog_start_date,
        "preview": "n"
    }
    config_save = os.path.expanduser("~/.fsrs4anki_optimizer")
    with open(config_save, "w+") as f:
        json.dump(remembered_fallbacks, f)

    optimized_out_path = f"{tmp_dir_path}/tempresult.json"

    def on_complete():
        with open(optimized_out_path, "r") as f:
            result = f.read()

        # Very dirty way of setting the decks name, todo: change this
        result = result.split("\n")
        result[3] = f'"deckName": "{name}",'
        result = "\n".join(result)

        saved_results_path = f"{dir_path}/saved.json"

        try:
            with open(saved_results_path, "r+") as f:
                saved_results = json.load(f)
        except FileNotFoundError:
            saved_results = dict()

        saved_results[did] = result

        contents = '\n'.join(saved_results.values())
        output = f"const deckParams = [\n{contents}]" 

        showInfo(output)

        with open(saved_results_path, "w+") as f:
            json.dump(saved_results, f)

        shutil.rmtree(tmp_dir_path)

    # Cant just call the library functions directly without anki freezing
    print(" ".join([sys.executable, "-m", "fsrs4anki_optimizer", filepath, "-y", "-o", optimized_out_path]))
    _worker.work(
        [sys.executable, "-m", "fsrs4anki_optimizer", filepath, "-y", "-o", optimized_out_path],
        on_complete,
        f"Optimizing {name}"
    )

def install(_):
    global _worker

    confirmed = askUser(
"""This will install the optimizer onto your system.
This will occupy 0.5-1GB of space and can take some time.
Please dont close anki until the popup arrives telling you its complete

There are other options if you just need to optimize a few decks
(consult https://github.com/open-spaced-repetition/fsrs4anki/releases)

Proceed?""",
title="Install local optimizer?")

    if confirmed: 
        _worker.work(
            [sys.executable, "-m", "pip", "install", 
                'fsrs4anki_optimizer @ git+https://github.com/open-spaced-repetition/fsrs4anki@v3.18.1#subdirectory=package',
                ],
                lambda: showInfo("Optimizer installed successfully, restart for it to take effect"),
                "Installing optimizer"
            )
