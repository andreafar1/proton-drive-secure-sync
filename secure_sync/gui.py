"""GTK3 v0.3: browsable, non-destructive Rclone UI. No credentials stored."""
import threading
from datetime import datetime
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk
from .core import RcloneClient, SyncError

CSS = b"""
window { background: #f5f5f8; }
headerbar { background: #2b2731; color: white; }
.sidebar { background: #efedf5; border-right: 1px solid #dedbe6; }
.brand { font-size: 20px; font-weight: 700; color: #43257e; }
.heading { font-size: 17px; font-weight: 700; }
.safe { color: #207743; font-weight: bold; }
.status { color: #514b5a; }
treeview:selected { background: #8050c7; }
button.suggested-action { background: #7141b5; color: white; }
"""
class Window(Gtk.Window):
    def __init__(self):
        super().__init__(title='Proton Drive Secure Sync v0.3')
        self.set_default_size(1020, 680)
        self.entries = []
        self.folder = ''
        self.busy = False
        self.events = []
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(root)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        side.get_style_context().add_class('sidebar')
        side.set_border_width(18)
        side.set_size_request(215, -1)
        root.pack_start(side, False, False, 0)
        brand = Gtk.Label(label='☁  Proton Drive\nSecure Sync  v0.3')
        brand.get_style_context().add_class('brand')
        brand.set_xalign(0)
        side.pack_start(brand, False, False, 8)
        for label, action in [('📁  File remoti', self.show_files),
                              ('⇅  Trasferimenti', self.show_transfers),
                              ('☷  Registro', self.show_log),
                              ('⚙  Impostazioni', self.show_settings),
                              ('ⓘ  Informazioni', self.show_info)]:
            button = Gtk.Button(label=label)
            button.connect('clicked', action)
            side.pack_start(button, False, False, 0)
        side.pack_end(Gtk.Label(label='✓ Modalità sicura\nNessuna cancellazione automatica\nNessuna sovrascrittura'), False, False, 6)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main.set_border_width(15)
        root.pack_start(main, True, True, 0)
        toolbar = Gtk.Box(spacing=8)
        main.pack_start(toolbar, False, False, 0)
        toolbar.pack_start(Gtk.Label(label='Remoto Rclone:'), False, False, 0)
        self.remote = Gtk.Entry()
        self.remote.set_text('proton:')
        self.remote.set_width_chars(17)
        toolbar.pack_start(self.remote, False, False, 0)
        for title, action in [('⟳ Aggiorna', self.refresh), ('↓ Scarica', self.download), ('↑ Carica', self.upload)]:
            b = Gtk.Button(label=title)
            b.connect('clicked', action)
            toolbar.pack_start(b, False, False, 0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        main.pack_start(self.stack, True, True, 0)
        filepage = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        nav = Gtk.Box(spacing=8)
        filepage.pack_start(nav, False, False, 0)
        up = Gtk.Button(label='↑ Cartella superiore')
        up.connect('clicked', self.go_up)
        nav.pack_start(up, False, False, 0)
        self.breadcrumb = Gtk.Label(label='Percorso: /')
        self.breadcrumb.set_xalign(0)
        nav.pack_start(self.breadcrumb, True, True, 0)
        self.store = Gtk.ListStore(str, str, str, str, str)
        self.tree = Gtk.TreeView(model=self.store)
        for i, title in enumerate(('Nome', 'Dimensione', 'Ultima modifica')):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            self.tree.append_column(col)
        self.tree.connect('row-activated', self.open_row)
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.tree)
        filepage.pack_start(scroll, True, True, 0)
        self.stack.add_titled(filepage, 'files', 'File remoti')
        logpage = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        logtitle = Gtk.Label(label='Registro delle operazioni (solo sessione corrente)')
        logtitle.get_style_context().add_class('heading')
        logpage.pack_start(logtitle, False, False, 0)
        self.logview = Gtk.TextView()
        self.logview.set_editable(False)
        self.logview.set_cursor_visible(False)
        logscroll = Gtk.ScrolledWindow()
        logscroll.add(self.logview)
        logpage.pack_start(logscroll, True, True, 0)
        self.stack.add_titled(logpage, 'log', 'Registro')
        self.info = Gtk.Label(label='Client sperimentale v0.3\nUsa un remoto Rclone configurato separatamente.\nNessuna sincronizzazione automatica, cancellazione o sovrascrittura.\nSHA-256 locale NON autentica il contenuto remoto.\nProvare solo con dati sacrificabili.')
        self.info.set_line_wrap(True)
        self.stack.add_titled(self.info, 'info', 'Informazioni')
        self.status = Gtk.Label(label='Pronto · solo upload/download manuali')
        self.status.set_xalign(0)
        self.status.get_style_context().add_class('status')
        main.pack_start(self.status, False, False, 0)
        self.record('Applicazione avviata (v0.3)')
    def record(self, message):
        self.events.append('[' + datetime.now().strftime('%H:%M:%S') + '] ' + message)
        self.logview.get_buffer().set_text('\n'.join(self.events[-500:]))
    def show_files(self, *_): self.stack.set_visible_child_name('files')
    def show_transfers(self, *_): self.stack.set_visible_child_name('log')
    def show_log(self, *_): self.stack.set_visible_child_name('log')
    def show_settings(self, *_):
        self.stack.set_visible_child_name('info')
        self.status.set_text('Imposta il nome del remoto Rclone nella barra superiore')
    def show_info(self, *_): self.stack.set_visible_child_name('info')
    def client(self): return RcloneClient(self.remote.get_text().strip())
    def task(self, label, action, done=None):
        if self.busy:
            self.status.set_text('Operazione in corso; attendere')
            return
        self.busy = True
        self.status.set_text(label + '…')
        self.record(label + ' avviato')
        def worker():
            try:
                result = action()
                GLib.idle_add(self.finish, label, result, done, None)
            except Exception as exc:
                GLib.idle_add(self.finish, label, None, done, str(exc))
        threading.Thread(target=worker, daemon=True).start()
    def finish(self, label, result, done, error):
        self.busy = False
        if error:
            self.status.set_text('Errore: ' + error)
            self.record(label + ' fallito: ' + error)
        else:
            if done: done(result)
            self.status.set_text(label + ' completato')
            self.record(label + ' completato')
        return False
    def refresh(self, *_):
        try: client = self.client()
        except SyncError as e:
            self.status.set_text(str(e)); return
        self.task('Lettura file remoti', client.list_entries, self.set_entries)
    def set_entries(self, entries):
        self.entries = entries
        self.render_folder()
    def render_folder(self):
        self.store.clear()
        prefix = self.folder + '/' if self.folder else ''
        self.breadcrumb.set_text('Percorso: /' + self.folder)
        for item in self.entries:
            path = item['path']
            if not path.startswith(prefix): continue
            tail = path[len(prefix):]
            if '/' in tail or not tail: continue
            is_dir = item['is_dir']
            size = '—' if is_dir else str(item['size'])
            modified = item['modified'][:16].replace('T', ' ')
            self.store.append([('📁 ' if is_dir else '📄 ') + tail, size, modified, path, 'dir' if is_dir else 'file'])
    def open_row(self, tree, path, column):
        item = self.store[path]
        if item[4] == 'dir':
            self.folder = item[3]
            self.render_folder()
    def go_up(self, *_):
        self.folder = self.folder.rpartition('/')[0]
        self.render_folder()
    def selected(self):
        model, itr = self.tree.get_selection().get_selected()
        return (model[itr][3], model[itr][4]) if itr is not None else (None, None)
    def confirm(self, verb, name):
        d = Gtk.MessageDialog(self, 0, Gtk.MessageType.QUESTION, Gtk.ButtonsType.OK_CANCEL,
                              verb + ' questo file?')
        d.format_secondary_text(name + '\nNessuna cancellazione o sovrascrittura automatica.')
        answer = d.run()
        d.destroy()
        return answer == Gtk.ResponseType.OK
    def upload(self, *_):
        chooser = Gtk.FileChooserDialog('Seleziona file', self, Gtk.FileChooserAction.OPEN,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        ok = chooser.run() == Gtk.ResponseType.OK
        filename = chooser.get_filename() if ok else None
        chooser.destroy()
        if not filename or not self.confirm('Caricare', Path(filename).name): return
        try:
            client = self.client()
            # Uploads to remote root only; no hidden path rewriting.
            self.task('Caricamento', lambda: client.upload(Path(filename)), lambda _: self.refresh())
        except SyncError as e: self.status.set_text(str(e))
    def download(self, *_):
        path, kind = self.selected()
        if not path or kind != 'file':
            self.status.set_text('Seleziona un file, non una cartella'); return
        chooser = Gtk.FileChooserDialog('Cartella di destinazione', self, Gtk.FileChooserAction.SELECT_FOLDER,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        ok = chooser.run() == Gtk.ResponseType.OK
        folder = chooser.get_filename() if ok else None
        chooser.destroy()
        if not folder or not self.confirm('Scaricare', path): return
        try:
            client = self.client()
            self.task('Download', lambda: client.download(path, Path(folder)))
        except SyncError as e: self.status.set_text(str(e))

def main():
    win = Window()
    win.connect('destroy', Gtk.main_quit)
    win.show_all()
    Gtk.main()
