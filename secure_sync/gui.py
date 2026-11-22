"""Small GTK3 interface; manual operations only."""
import threading
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from .core import RcloneClient, SyncError

class Window(Gtk.Window):
    def __init__(self):
        super().__init__(title='Proton Drive Secure Sync — 0.2')
        self.set_default_size(760, 480)
        self.client = None
        self.files = []
        self.busy = False
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        self.add(box)
        box.pack_start(Gtk.Label(label='Manual transfers only · No automatic sync · No delete'), False, False, 0)
        bar = Gtk.Box(spacing=8)
        box.pack_start(bar, False, False, 0)
        self.remote = Gtk.Entry()
        self.remote.set_text('proton:')
        self.remote.set_placeholder_text('Configured Rclone remote (e.g. proton:)')
        bar.pack_start(self.remote, True, True, 0)
        for title, callback in [('List remote files', self.refresh), ('Upload file', self.upload), ('Download selected', self.download)]:
            btn = Gtk.Button(label=title)
            btn.connect('clicked', callback)
            bar.pack_start(btn, False, False, 0)
        self.store = Gtk.ListStore(str, str)
        self.tree = Gtk.TreeView(model=self.store)
        for i, title in enumerate(['Remote path', 'Bytes']):
            self.tree.append_column(Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i))
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.tree)
        box.pack_start(scroll, True, True, 0)
        self.status = Gtk.Label(label='Configure your Rclone remote first; then list files.')
        self.status.set_xalign(0)
        box.pack_start(self.status, False, False, 0)

    def task(self, work, done=None):
        if self.busy:
            self.status.set_text('A transfer is already in progress')
            return
        self.busy = True
        self.status.set_text('Working…')
        def run():
            try:
                value = work()
                GLib.idle_add(self.complete, value, done, None)
            except Exception as exc:
                GLib.idle_add(self.complete, None, done, str(exc))
        threading.Thread(target=run, daemon=True).start()

    def complete(self, value, done, error):
        self.busy = False
        if error:
            self.status.set_text('Error: ' + error)
        else:
            if done:
                done(value)
            self.status.set_text('Completed successfully')
        return False

    def get_client(self):
        return RcloneClient(self.remote.get_text().strip())

    def refresh(self, *_):
        try:
            client = self.get_client()
        except SyncError as e:
            self.status.set_text(str(e))
            return
        def done(files):
            self.store.clear()
            for item in files:
                self.store.append([item['path'], str(item['size'])])
        self.task(client.list_files, done)

    def confirm(self, action, filename):
        dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.QUESTION,
                                   Gtk.ButtonsType.OK_CANCEL,
                                   f'{action} this file?')
        dialog.format_secondary_text(filename + '\nNo automatic deletion is performed.')
        result = dialog.run()
        dialog.destroy()
        return result == Gtk.ResponseType.OK

    def upload(self, *_):
        chooser = Gtk.FileChooserDialog('Select file to upload', self, Gtk.FileChooserAction.OPEN,
                                        (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        response = chooser.run()
        path = chooser.get_filename() if response == Gtk.ResponseType.OK else None
        chooser.destroy()
        if path and self.confirm('Upload', Path(path).name):
            try:
                client = self.get_client()
                self.task(lambda: client.upload(Path(path)))
            except SyncError as e:
                self.status.set_text(str(e))

    def download(self, *_):
        model, iterator = self.tree.get_selection().get_selected()
        if iterator is None:
            self.status.set_text('Select a remote file first')
            return
        remote_path = model[iterator][0]
        chooser = Gtk.FileChooserDialog('Choose download directory', self, Gtk.FileChooserAction.SELECT_FOLDER,
                                        (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        response = chooser.run()
        directory = chooser.get_filename() if response == Gtk.ResponseType.OK else None
        chooser.destroy()
        if directory and self.confirm('Download', remote_path):
            try:
                client = self.get_client()
                self.task(lambda: client.download(remote_path, Path(directory)))
            except SyncError as e:
                self.status.set_text(str(e))

def main():
    win = Window()
    win.connect('destroy', Gtk.main_quit)
    win.show_all()
    Gtk.main()
