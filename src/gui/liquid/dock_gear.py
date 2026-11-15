from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QRectF,
    QSize,
    QVariantAnimation,
)
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import QApplication

from awesomeui.liquid.controls import GlassPanel, LiquidButton
from src.gui.theme import ColorThemeManager, theme_pixmap


class GearButton(LiquidButton):
    def __init__(self,parent=None):
        super().__init__('',parent)
        self.setProperty('dockReveal',0.0)
        self.setProperty('dockCollapsedWidth',52)
        self._spin_progress=1.0
        self._spin=QVariantAnimation(self)
        self._spin.setDuration(650)
        self._spin.setStartValue(0.0)
        self._spin.setEndValue(1.0)
        self._spin.setEasingCurve(QEasingCurve.OutCubic)
        self._spin.valueChanged.connect(self._spin_step)

    def _spin_step(self,value):
        self._spin_progress=float(value)
        if QApplication.instance().property('liquid_reduce_motion'):
            self._spin.stop()
            self._spin_progress=1.0
        self.update()

    def enterEvent(self,event):
        super().enterEvent(event)
        if not QApplication.instance().property('liquid_reduce_motion'):
            self._spin.stop()
            self._spin_progress=0.0
            self._spin.start()

    def hideEvent(self,event):
        self._spin.stop()
        self._spin_progress=1.0
        super().hideEvent(event)

    def paint_icon(self,painter,rect):
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.translate(rect.center())
        painter.rotate(360*self._spin_progress if self._spin_progress<1 else 0)
        super().paint_icon(painter,QRectF(-rect.width()/2,-rect.height()/2,rect.width(),rect.height()))
        painter.restore()


class DockGear(QObject):
    """Settings gear floating over the dock's corner."""
    def __init__(self,window):
        super().__init__(window)
        self.window=window
        self.settings_frame=GlassPanel(window)
        settings=self.main_settings=GearButton(self.settings_frame)
        settings.setProperty('dockItem',True)
        settings.setText('Settings')
        settings.setAccessibleName('Application settings')
        settings.setToolTip('')
        settings.setIcon(QIcon(theme_pixmap(':/icon/gear.svg',ColorThemeManager.instance().colors.text_primary,116)))
        settings.clicked.connect(lambda:window.bottom_navigation.navigate(4))
        settings.setGeometry(0,0,52,48)
        settings.setIconSize(QSize(29,29))
        settings.show()
        self._corner_motion=QVariantAnimation(self)
        self._corner_motion.setEasingCurve(QEasingCurve.OutCubic)
        self._corner_motion.valueChanged.connect(self._corner_step)
        QApplication.instance().installEventFilter(self)
        ColorThemeManager.instance().theme_changed.connect(self.retheme)

    def retheme(self):
        self.main_settings.setIcon(QIcon(theme_pixmap(':/icon/gear.svg',ColorThemeManager.instance().colors.text_primary,116)))

    def _corner_step(self,value):
        self.main_settings.setProperty('dockReveal',float(value))
        self.position()
        self.main_settings.update()

    def _reveal_corner(self,expanded):
        motion=self._corner_motion
        motion.stop()
        motion.setDuration(0 if QApplication.instance().property('liquid_reduce_motion') else 240)
        motion.setStartValue(float(self.main_settings.property('dockReveal')))
        motion.setEndValue(1.0 if expanded else 0.0)
        motion.start()

    def position(self):
        dock=self.window.bottom_navigation
        width=round(52+(self.main_settings.fontMetrics().horizontalAdvance(self.main_settings.text())+14)*float(self.main_settings.property('dockReveal')))
        x=max(8,self.window.width()-width-16)
        y=16 if dock.edge in ('top','left','right') else max(8,self.window.height()-64)
        if dock.edge=='right':
            x=16
        self.settings_frame.setGeometry(x,y,width,48)
        self.main_settings.setGeometry(self.settings_frame.rect())
        self.settings_frame.show()
        self.settings_frame.raise_()

    def eventFilter(self,target,event):
        if target is self.window and event.type()==QEvent.Hide:
            self._corner_motion.stop()
            self.main_settings.setProperty('dockReveal',0.0)
        if target is self.main_settings:
            if event.type()==QEvent.ToolTip:
                return True
            if event.type() in (QEvent.Enter,QEvent.FocusIn):
                self._reveal_corner(True)
            elif event.type() in (QEvent.Leave,QEvent.FocusOut):
                self._reveal_corner(False)
        return False
