from .utils import *
from .configuration import *

from anki.decks import DeckManager
from aqt.qt import QThreadPool, QRunnable, QObject, pyqtSignal, QDialog
from aqt.utils import showInfo, showCritical, askUserDialog
import aqt
import aqt.forms

import time

class InstallerQDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.form = aqt.forms.synclog.Ui_Dialog()
        self.form.setupUi(self)
        self.form.plainTextEdit.setPlainText("Installing optimizer...")
        self.show()

    def _on_log_entry(self, entry) -> None:
        self.form.plainTextEdit.appendPlainText(entry)


config = Config()

class Progress(QObject):
    progress = pyqtSignal(int, int)
    critical = pyqtSignal(str)

    @staticmethod
    def tooltip(n, total):
        tooltip(f"{_stage}: {n}/{total} {100 * n/total}%")


update_period = 0.1 # how long the progress tooltips are refreshed in seconds
_progress = Progress()
_progress.progress.connect(Progress.tooltip)
_progress.critical.connect(showCritical)
_stage = "Error"

_optimizing = False

def optimize(did: int):
    global _optimizing

    if not _optimizing:
        _optimizing = True
        try:
            _optimize(did)
        except:
            _optimizing = False
    else:
        showWarning("A deck is already optimizing please wait.")

def _optimize(did: int):

    manager = DeckManager(mw.col)
    deck = manager.get(did)
    assert deck
    name = deck["name"]

    preferences = mw.col.get_preferences()

    # https://stackoverflow.com/questions/1111056/get-time-zone-information-of-the-system-in-python/10854983#10854983
    offset = time.timezone if (time.localtime().tm_isdst == 0) else time.altzone
    offset = offset / 60 / 60 * -1

    timezone = f"Etc/GMT{'+' if offset >= 0 else ''}{int(offset)}" # Maybe make this overridable?
    print(timezone)
    revlog_start_date = "2000-01-01" # TODO: implement this as a config option
    rollover = preferences.scheduling.rollover

    diag = askUserDialog("Find optimal retention? (This takes an extra long time)", ["Yes", "No", "Cancel"])
    diag.setDefault(1)
    resp = diag.run()

    if resp == "Cancel": # If they hit cancel
        tooltip("Optimization cancelled")
        return
    else:
        get_optimal_retention = resp == "Yes" # If they didn't hit cancel convert answer to bool

    class OptimizeWorker(QRunnable):
        class Events(QObject):
            finished = pyqtSignal(dict)
            stage = pyqtSignal(str)
        
        events = Events()

        def run(self):
            revlogs = mw.col.db.all(f"""
SELECT revlog.* FROM revlog
JOIN cards on revlog.cid = cards.id
WHERE cards.did in {mw.col.sched._deck_limit():s}
""")

            COLUMNS = ["id", "cid", "usn", "ease", "ivl", "lastIvl", "factor", "time", "type"]

            revlogs = [{k: v for k,v in zip(COLUMNS, value)} for value in revlogs]

            from .fsrs_optimizer_rust import train

            w = train(revlogs)

            result = {
                # Calculated
                "name": name,
                "w": w,
                REQUEST_RETENTION: 0.8,
                RETENTION_IS_NOT_OPTIMIZED: True,
                
                # Defaults
                MAX_INTERVAL: 36500, 
                EASY_BONUS: 1.3,
                HARD_INTERVAL: 1.2
                }

            self.events.finished.emit(result)

    def on_complete(result: dict[str]):
        global _optimizing

        _optimizing = False

        config.load()

        saved_results = config.saved_optimized
        saved_results[did] = result
        config.saved_optimized = saved_results

        showInfo(config.results_string())

        # shutil.rmtree(tmp_dir_path)

    # Uses workers to avoid blocking main thread
    worker = OptimizeWorker()
    worker.events.finished.connect(on_complete)

    def on_stage(stage):
        global _stage
        tooltip(stage)
        _stage = stage

    worker.events.stage.connect(on_stage)

    QThreadPool.globalInstance().start(worker)
