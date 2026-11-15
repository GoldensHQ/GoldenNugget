import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

app = QApplication([])

import src.gui.notifications as notifications

notifications._last = None
shown = []


class FakeTray:
    def showMessage(self, title, message, icon, msecs):
        shown.append((title, message))


notifications._tray = FakeTray()

notifications.notify('A', 'first')
notifications.notify('A', 'first')  # identical repeat stays silent
assert shown == [('A', 'first')], shown

clicked = []
notifications.notify('B', 'second', lambda: clicked.append(True))
assert shown[-1] == ('B', 'second'), shown
notifications._clicked()
assert clicked == [True], clicked
notifications._clicked()  # one-shot action
assert clicked == [True], clicked

print('native notifications OK')
