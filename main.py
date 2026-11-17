import bisect
import json
import os
import re
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from pygments import lex
    from pygments.lexers import TextLexer, get_lexer_for_filename
    from pygments.styles import get_style_by_name
    from pygments.util import ClassNotFound

    STYLE = get_style_by_name("monokai")
    BG = STYLE.background_color
except ImportError:
    STYLE = None
    BG = "#272822"

APP_NAME = "CSU"
CONFIG_DIR = Path(os.getenv("APPDATA") or Path.home() / ".config") / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
FG = "#f8f8f2"
PANEL_BG = "#252526"
ACTIVE_BG = BG
INACTIVE_BG = "#2d2d30"
FONT = ("Consolas", 11)
MAX_FILE_SIZE = 5 * 1024 * 1024
DUMMY = "<loading>"

COLORS = {"comment": "#75715e", "string": "#e6db74", "number": "#ae81ff", "keyword": "#f92672"}
KEYWORDS = (
    "and|as|assert|async|await|break|case|catch|class|const|continue|def|default|del|do|elif|else|"
    "enum|except|export|extends|false|False|finally|fn|for|from|func|function|global|if|implements|"
    "import|in|interface|is|lambda|let|namespace|new|nil|None|not|null|or|package|pass|private|"
    "public|raise|return|self|static|struct|super|switch|this|throw|true|True|try|typeof|using|"
    "var|void|while|with|yield"
)
TOKEN_RE = re.compile("|".join([
    r"(?P<comment>#[^\n]*|//[^\n]*|--[^\n]*|/\*.*?\*/)",
    r"(?P<string>\"\"\".*?\"\"\"|'''.*?'''|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)",
    r"(?P<number>\b\d+(?:\.\d+)?\b)",
    rf"(?P<keyword>\b(?:{KEYWORDS})\b)",
]), re.S)


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", app_dir())
    return os.path.join(base, name)


ICON_PATH = resource_path("icon.ico")
LOG_PATH = os.path.join(app_dir(), "csu_error.log")


def python_executable() -> str:
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[:-5] + ".exe"
    return exe


RUNNERS = {
    ".py": [python_executable()],
    ".js": ["node"],
    ".ps1": ["powershell", "-ExecutionPolicy", "Bypass", "-File"],
    ".vbs": ["cscript", "//nologo"],
    ".bat": [],
    ".cmd": [],
    ".exe": [],
}


def pygments_tokens(path: str, content: str):
    options = {"stripnl": False, "ensurenl": False}
    try:
        lexer = get_lexer_for_filename(path, content, **options)
    except ClassNotFound:
        lexer = TextLexer(**options)
    line, col = 1, 0
    for token, value in lex(content, lexer):
        parts = value.split("\n")
        end_line = line + len(parts) - 1
        end_col = len(parts[-1]) + (col if len(parts) == 1 else 0)
        color = STYLE.style_for_token(token)["color"]
        if color:
            yield str(token), f"#{color}", f"{line}.{col}", f"{end_line}.{end_col}"
        line, col = end_line, end_col


def regex_tokens(_path: str, content: str):
    starts = [0] + [m.end() for m in re.finditer("\n", content)]

    def index(offset: int) -> str:
        line = bisect.bisect_right(starts, offset)
        return f"{line}.{offset - starts[line - 1]}"

    for match in TOKEN_RE.finditer(content):
        kind = match.lastgroup
        yield kind, COLORS[kind], index(match.start()), index(match.end())


def iter_tokens(path: str, content: str):
    if STYLE:
        try:
            yield from pygments_tokens(path, content)
            return
        except Exception:
            pass
    yield from regex_tokens(path, content)


def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


class CodeView(tk.Frame):
    def __init__(self, master, path: str, content: str, on_change=None):
        super().__init__(master, bg=BG)
        self.path = path
        self.dirty = False
        self.newline = "\n"
        self.on_change = on_change
        self._tags: set[str] = set()
        self._lines = 0
        self._after_id = None

        self.scrollbar = ttk.Scrollbar(self, command=self._on_scrollbar)
        self.scrollbar.pack(side="right", fill="y")

        self.numbers = tk.Text(
            self, width=5, padx=6, bg=PANEL_BG, fg="#858585", font=FONT,
            relief="flat", state="disabled", cursor="arrow", takefocus=0,
        )
        self.numbers.pack(side="left", fill="y")
        self.numbers.tag_configure("right", justify="right")
        for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.numbers.bind(event, lambda _e: "break")

        self.text = tk.Text(
            self, wrap="none", bg=BG, fg=FG, insertbackground=FG, font=FONT,
            relief="flat", undo=True, selectbackground="#49483e",
            inactiveselectbackground="#49483e", yscrollcommand=self._on_text_scroll,
        )
        self.text.pack(side="left", fill="both", expand=True)

        self.text.insert("1.0", content)
        self._highlight()
        self._update_numbers()
        self.text.edit_reset()
        self.text.edit_modified(False)

        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<Control-a>", self._select_all)
        self.text.bind("<Control-A>", self._select_all)
        self.text.bind("<Control-KeyPress>", self._on_ctrl_key)

    def destroy(self):
        if self._after_id:
            self.after_cancel(self._after_id)
        super().destroy()

    def _on_scrollbar(self, *args):
        self.text.yview(*args)

    def _on_text_scroll(self, first, last):
        self.scrollbar.set(first, last)
        self.numbers.yview_moveto(first)

    def _select_all(self, _event):
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "end-1c")
        return "break"

    def _on_ctrl_key(self, event):
        if os.name != "nt" or len(event.keysym) == 1:
            return None
        if event.keycode == 65:
            return self._select_all(event)
        sequence = {67: "<<Copy>>", 86: "<<Paste>>", 88: "<<Cut>>",
                    90: "<<Undo>>", 89: "<<Redo>>"}.get(event.keycode)
        if sequence:
            self.text.event_generate(sequence)
            return "break"
        return None

    def _on_modified(self, _event):
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self._update_numbers()
        if not self.dirty:
            self.dirty = True
            if self.on_change:
                self.on_change()
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(300, self._highlight)

    def _update_numbers(self):
        count = int(self.text.index("end-1c").split(".")[0])
        if count == self._lines:
            return
        self._lines = count
        self.numbers.configure(state="normal")
        self.numbers.delete("1.0", "end")
        self.numbers.insert("1.0", "\n".join(map(str, range(1, count + 1))), "right")
        self.numbers.configure(state="disabled")
        self.numbers.yview_moveto(self.text.yview()[0])

    def _highlight(self):
        self._after_id = None
        content = self.text.get("1.0", "end-1c")
        for tag in self._tags:
            self.text.tag_remove(tag, "1.0", "end")
        for tag, color, start, end in iter_tokens(self.path, content):
            if tag not in self._tags:
                self.text.tag_configure(tag, foreground=color)
                self._tags.add(tag)
            self.text.tag_add(tag, start, end)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x700")
        self.configure(bg=PANEL_BG)
        self._set_icon()
        self.config_data = load_config()
        self.tabs: dict[str, dict] = {}
        self.active: str | None = None

        self._setup_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Control-KeyPress>", self._on_ctrl_key)
        self.bind("<F5>", lambda _e: self.run_active())

        project = self.config_data.get("project")
        if project and os.path.isdir(project):
            self.load_project(project)

    def _set_icon(self):
        if not os.path.exists(ICON_PATH):
            return
        try:
            self.iconbitmap(default=ICON_PATH)
        except tk.TclError:
            pass

    def _setup_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", background=PANEL_BG, fieldbackground=PANEL_BG,
                        foreground=FG, borderwidth=0, rowheight=24)
        style.map("Treeview", background=[("selected", "#094771")])

    def _build_ui(self):
        paned = tk.PanedWindow(self, orient="horizontal", sashwidth=4, bg="#111111", bd=0)
        paned.pack(fill="both", expand=True)

        left = tk.Frame(paned, bg=PANEL_BG)
        paned.add(left, minsize=180, width=280)
        ttk.Button(left, text="Открыть проект", command=self.choose_project).pack(fill="x", padx=6, pady=6)

        buttons = [
            [("Новый файл", lambda: self.create_entry(False)), ("Новая папка", lambda: self.create_entry(True))],
            [("Переименовать", self.rename_entry), ("Удалить", self.delete_entries)],
        ]
        for row in buttons:
            actions = tk.Frame(left, bg=PANEL_BG)
            actions.pack(fill="x", padx=6, pady=(0, 6))
            for i, (text, command) in enumerate(row):
                ttk.Button(actions, text=text, command=command).pack(
                    side="left", expand=True, fill="x", padx=(0 if i == 0 else 4, 0))

        self.project_label = tk.Label(left, text="Проект не выбран", bg=PANEL_BG, fg="#cccccc", anchor="w")
        self.project_label.pack(fill="x", padx=6)

        tree_frame = tk.Frame(left, bg=PANEL_BG)
        tree_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="extended")
        scroll = ttk.Scrollbar(tree_frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewOpen>>", self.on_tree_open)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<F2>", lambda _e: self.rename_entry())
        self.tree.bind("<Delete>", lambda _e: self.delete_entries())

        right = tk.Frame(paned, bg=BG)
        paned.add(right, minsize=300)
        self.tab_bar = tk.Frame(right, bg=PANEL_BG)
        self.tab_bar.pack(fill="x")
        ttk.Button(self.tab_bar, text="Запуск (F5)", command=self.run_active).pack(side="right", padx=4, pady=2)
        self.content = tk.Frame(right, bg=BG)
        self.content.pack(fill="both", expand=True)

    def choose_project(self):
        path = filedialog.askdirectory(title="Выберите папку проекта",
                                       initialdir=self.config_data.get("project"))
        if path:
            self.load_project(os.path.normpath(path))

    def load_project(self, path: str):
        for tab_path in list(self.tabs):
            if not self.close_tab(tab_path):
                return
        self.config_data["project"] = path
        save_config(self.config_data)
        self.project_label.configure(text=os.path.basename(path) or path)
        self.tree.delete(*self.tree.get_children())
        self._populate(path, "")

    def _populate(self, directory: str, parent: str):
        try:
            entries = sorted(os.scandir(directory), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            return
        for entry in entries:
            self.tree.insert(parent, "end", iid=entry.path, text=entry.name)
            if entry.is_dir():
                self.tree.insert(entry.path, "end", iid=f"{entry.path}{os.sep}{DUMMY}", text="")

    def _load_children(self, iid: str):
        children = self.tree.get_children(iid)
        if len(children) == 1 and children[0].endswith(DUMMY):
            self.tree.delete(children[0])
            self._populate(iid, iid)

    def on_tree_open(self, _event):
        self._load_children(self.tree.focus())

    def on_tree_select(self, _event):
        selection = self.tree.selection()
        if len(selection) == 1 and os.path.isfile(selection[0]):
            self.open_file(selection[0])

    def create_entry(self, is_dir: bool):
        project = self.config_data.get("project")
        if not project or not os.path.isdir(project):
            messagebox.showwarning(APP_NAME, "Сначала откройте проект")
            return

        selection = self.tree.selection()
        base = selection[0] if selection else project
        if os.path.isfile(base):
            base = os.path.dirname(base)

        kind = "папки" if is_dir else "файла"
        name = simpledialog.askstring(
            APP_NAME,
            f"Путь {kind} внутри «{os.path.relpath(base, project)}»:\n(например: folder/folder/file.txt)",
            parent=self,
        )
        if not name or not name.strip():
            return

        target = os.path.normpath(os.path.join(base, name.strip()))
        try:
            inside = os.path.commonpath([project, target]) == project and target != project
        except ValueError:
            inside = False
        if not inside:
            messagebox.showerror(APP_NAME, "Путь должен находиться внутри проекта")
            return
        if os.path.exists(target):
            messagebox.showerror(APP_NAME, "Такой файл или папка уже существует")
            return

        try:
            if is_dir:
                os.makedirs(target)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                open(target, "x").close()
        except OSError as error:
            messagebox.showerror(APP_NAME, str(error))
            return

        base_iid = "" if base == project else base
        self.tree.delete(*self.tree.get_children(base_iid))
        self._populate(base, base_iid)
        if base_iid:
            self.tree.item(base_iid, open=True)
        current = base
        for part in os.path.relpath(target, base).split(os.sep)[:-1]:
            current = os.path.join(current, part)
            self._load_children(current)
            self.tree.item(current, open=True)
        self.tree.selection_set(target)
        self.tree.see(target)

    def _tabs_under(self, path: str) -> list[str]:
        return [p for p in self.tabs if p == path or p.startswith(path + os.sep)]

    def _refresh(self, directory: str):
        iid = "" if directory == self.config_data["project"] else directory
        opened, stack = [], list(self.tree.get_children(iid))
        while stack:
            item = stack.pop()
            if self.tree.item(item, "open"):
                opened.append(item)
            stack.extend(self.tree.get_children(item))
        self.tree.delete(*self.tree.get_children(iid))
        self._populate(directory, iid)
        for item in sorted(opened, key=len):
            if self.tree.exists(item):
                self._load_children(item)
                self.tree.item(item, open=True)

    def rename_entry(self):
        selection = self.tree.selection()
        if len(selection) != 1:
            messagebox.showinfo(APP_NAME, "Выберите один файл или папку")
            return
        old = selection[0]
        new_name = simpledialog.askstring(APP_NAME, "Новое имя:", initialvalue=os.path.basename(old), parent=self)
        new_name = (new_name or "").strip()
        if not new_name or new_name == os.path.basename(old):
            return
        if "/" in new_name or "\\" in new_name:
            messagebox.showerror(APP_NAME, "Имя не должно содержать / или \\")
            return
        new = os.path.join(os.path.dirname(old), new_name)
        if os.path.exists(new) and not os.path.samefile(old, new):
            messagebox.showerror(APP_NAME, "Такой файл или папка уже существует")
            return

        affected = self._tabs_under(old)
        for tab_path in affected:
            if not self.close_tab(tab_path):
                return
        try:
            os.rename(old, new)
        except OSError as error:
            messagebox.showerror(APP_NAME, str(error))
            return
        self._refresh(os.path.dirname(old))
        if os.path.isfile(new) and old in affected:
            self.open_file(new)
        elif self.tree.exists(new):
            self.tree.selection_set(new)

    def delete_entries(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo(APP_NAME, "Выберите файлы или папки для удаления")
            return
        paths = [p for p in selection if not any(p.startswith(q + os.sep) for q in selection)]
        names = ", ".join(os.path.basename(p) for p in paths[:5]) + ("..." if len(paths) > 5 else "")
        if not messagebox.askyesno(APP_NAME, f"Удалить безвозвратно: {names}?", icon="warning"):
            return
        for path in paths:
            for tab_path in self._tabs_under(path):
                self.close_tab(tab_path, ask=False)
            try:
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except OSError as error:
                messagebox.showerror(APP_NAME, f"{path}\n{error}")
        for parent in {os.path.dirname(p) for p in paths}:
            self._refresh(parent)

    def open_file(self, path: str):
        if path in self.tabs:
            self.select_tab(path)
            return
        try:
            if os.path.getsize(path) > MAX_FILE_SIZE:
                raise ValueError("Файл слишком большой")
            with open(path, "rb") as f:
                data = f.read()
            if b"\0" in data:
                raise ValueError("Бинарный файл нельзя открыть")
            content = data.decode("utf-8", errors="replace")
            crlf = "\r\n" in content
            content = content.replace("\r\n", "\n")
        except (OSError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error))
            return

        header = tk.Frame(self.tab_bar, bg=INACTIVE_BG)
        header.pack(side="left", padx=(0, 1))
        label = tk.Label(header, text=os.path.basename(path), bg=INACTIVE_BG, fg=FG, padx=8, pady=4)
        label.pack(side="left")
        close = tk.Label(header, text="×", bg=INACTIVE_BG, fg="#aaaaaa", padx=6, cursor="hand2",
                         font=("Segoe UI", 12))
        close.pack(side="left")
        label.bind("<Button-1>", lambda _e: self.select_tab(path))
        close.bind("<Button-1>", lambda _e: self.close_tab(path))
        close.bind("<Enter>", lambda _e: close.configure(fg="#ffffff"))
        close.bind("<Leave>", lambda _e: close.configure(fg="#aaaaaa"))

        view = CodeView(self.content, path, content, on_change=lambda: self._refresh_title(path))
        view.newline = "\r\n" if crlf else "\n"
        self.tabs[path] = {"header": header, "view": view, "label": label}
        self.select_tab(path)

    def select_tab(self, path: str):
        if self.active in self.tabs:
            self.tabs[self.active]["view"].pack_forget()
            self._paint_header(self.active, INACTIVE_BG)
        self.active = path
        self.tabs[path]["view"].pack(fill="both", expand=True)
        self._paint_header(path, ACTIVE_BG)

    def _paint_header(self, path: str, color: str):
        header = self.tabs[path]["header"]
        header.configure(bg=color)
        for child in header.winfo_children():
            child.configure(bg=color)

    def _refresh_title(self, path: str):
        tab = self.tabs[path]
        tab["label"].configure(text=("* " if tab["view"].dirty else "") + os.path.basename(path))

    def save_file(self, path: str) -> bool:
        view = self.tabs[path]["view"]
        try:
            with open(path, "w", encoding="utf-8", newline=view.newline) as f:
                f.write(view.text.get("1.0", "end-1c"))
        except OSError as error:
            messagebox.showerror(APP_NAME, str(error))
            return False
        view.dirty = False
        self._refresh_title(path)
        return True

    def save_active(self):
        if self.active in self.tabs:
            self.save_file(self.active)

    def run_active(self):
        if self.active not in self.tabs:
            messagebox.showinfo(APP_NAME, "Откройте файл для запуска")
            return
        path = self.active
        if self.tabs[path]["view"].dirty and not self.save_file(path):
            return
        if os.name != "nt":
            messagebox.showinfo(APP_NAME, "Запуск через консоль поддерживается только в Windows")
            return
        prefix = RUNNERS.get(os.path.splitext(path)[1].lower())
        if prefix is None:
            messagebox.showinfo(APP_NAME, "Для этого типа файлов запуск не настроен")
            return
        command = subprocess.list2cmdline(prefix + [path])
        try:
            subprocess.Popen(f'cmd /k "{command}"', cwd=os.path.dirname(path),
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        except OSError as error:
            messagebox.showerror(APP_NAME, str(error))

    def _on_ctrl_key(self, event):
        if event.keysym.lower() == "s" or (os.name == "nt" and event.keycode == 83):
            self.save_active()

    def close_tab(self, path: str, ask: bool = True) -> bool:
        tab = self.tabs[path]
        if ask and tab["view"].dirty:
            self.select_tab(path)
            answer = messagebox.askyesnocancel(APP_NAME, f"Сохранить изменения в «{os.path.basename(path)}»?")
            if answer is None or (answer and not self.save_file(path)):
                return False
        self.tabs.pop(path)
        tab["view"].destroy()
        tab["header"].destroy()
        if self.active == path:
            self.active = None
            if self.tabs:
                self.select_tab(next(reversed(self.tabs)))
        return True

    def on_close(self):
        for path in list(self.tabs):
            if not self.close_tab(path):
                return
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(traceback.format_exc() + "\n")
        except OSError:
            pass
        raise