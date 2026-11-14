import os
import re
import json
import shutil
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


CONFIG_FILE = "settings.json"


class CodeEditor(ttk.Frame):
  def __init__(self, parent, file_path=None, app_instance=None):
    super().__init__(parent)
    self.file_path = file_path
    self.app_instance = app_instance

    self.header_frame = tk.Frame(self, bg="#2d2d2d")
    self.header_frame.pack(side=tk.TOP, fill=tk.X)

    file_title = os.path.basename(file_path) if file_path else "Untitled"
    self.title_label = tk.Label(
        self.header_frame, text=file_title, font=("Consolas", 10, "bold"),
        bg="#2d2d2d", fg="#cccccc"
    )
    self.title_label.pack(side=tk.LEFT, padx=8, pady=4)

    self.close_btn = tk.Button(
        self.header_frame, text="✕", width=3, command=self.close_tab,
        bg="#2d2d2d", fg="#cccccc", bd=0, activebackground="#3e3e42", activeforeground="white"
    )
    self.close_btn.pack(side=tk.RIGHT, padx=4)

    self.save_btn = tk.Button(
        self.header_frame, text="Save", command=self.save_file,
        bg="#3f3f46", fg="#cccccc", bd=0, padx=6, activebackground="#505054", activeforeground="white"
    )
    self.save_btn.pack(side=tk.RIGHT, padx=2)

    self.body_frame = tk.Frame(self, bg="#1e1e1e")
    self.body_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    self.text_widget = tk.Text(
        self.body_frame,
        wrap=tk.NONE,
        undo=True,
        bg="#1e1e1e",
        fg="#d4d4d4",
        insertbackground="#ffffff",
        font=("Consolas", 11),
        bd=0,
        highlightthickness=0,
    )

    self.line_numbers = tk.Canvas(
        self.body_frame, width=45, bg="#1e1e1e", bd=0, highlightthickness=0
    )

    self.scrollbar_y = ttk.Scrollbar(
        self.body_frame, orient="vertical", command=self.scroll_text
    )
    self.scrollbar_x = ttk.Scrollbar(
        self, orient="horizontal", command=self.text_widget.xview
    )

    self.text_widget.configure(
        yscrollcommand=self.on_text_scroll, xscrollcommand=self.scrollbar_x.set
    )

    self.scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
    self.scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
    self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
    self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    self.text_widget.tag_configure("keyword", foreground="#569cd6")
    self.text_widget.tag_configure("string", foreground="#ce9178")

    self.text_widget.bind("<KeyRelease>", self.on_key_release)
    self.text_widget.bind("<Tab>", self.insert_spaces)
    self.text_widget.bind("<Button-3>", self.show_editor_context_menu)

    if file_path and os.path.exists(file_path):
      try:
        with open(file_path, "r", encoding="utf-8") as f:
          self.text_widget.insert("1.0", f.read())
      except Exception as e:
        messagebox.showerror("Error", str(e))

    self.update_line_numbers()
    self.highlight()

  def scroll_text(self, *args):
    self.text_widget.yview(*args)
    self.update_line_numbers()

  def on_text_scroll(self, *args):
    self.scrollbar_y.set(*args)
    self.update_line_numbers()

  def update_line_numbers(self):
    self.line_numbers.delete("all")
    i = self.text_widget.index("@0,0")
    while True:
      dline = self.text_widget.dlineinfo(i)
      if dline is None:
        break
      y = dline[1]
      linenum = str(i).split(".")[0]
      self.line_numbers.create_text(
          40, y, anchor="ne", text=linenum, fill="#858585", font=("Consolas", 11)
      )
      i = self.text_widget.index(f"{i}+1line")

  def on_key_release(self, event=None):
    self.update_line_numbers()
    self.highlight()

  def insert_spaces(self, event):
    self.text_widget.insert("insert", "    ")
    return "break"

  def show_editor_context_menu(self, event):
    menu = tk.Menu(self, tearoff=0, bg="#2d2d2d", fg="#ffffff")
    menu.add_command(label="Вырезать", command=lambda: self.text_widget.event_generate("<<Cut>>"))
    menu.add_command(label="Копировать", command=lambda: self.text_widget.event_generate("<<Copy>>"))
    menu.add_command(label="Вставить", command=lambda: self.text_widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Выбрать всё", command=lambda: self.text_widget.tag_add("sel", "1.0", "end"))
    menu.tk_popup(event.x_root, event.y_root)

  def highlight(self):
    for tag in ["keyword", "string"]:
      self.text_widget.tag_remove(tag, "1.0", tk.END)

    content = self.text_widget.get("1.0", tk.END)

    for match in re.finditer(r'(\".*?\"|\'.*?\')', content):
      start = f"1.0 + {match.start()} chars"
      end = f"1.0 + {match.end()} chars"
      self.text_widget.tag_add("string", start, end)

    keywords = [
        "def", "class", "import", "from", "return", "if", "else", "elif",
        "for", "while", "in", "and", "or", "not", "True", "False", "None",
        "try", "except", "with", "as", "lambda", "pass", "break", "continue"
    ]
    for kw in keywords:
      for match in re.finditer(r"\b" + kw + r"\b", content):
        start = f"1.0 + {match.start()} chars"
        end = f"1.0 + {match.end()} chars"
        if "string" not in self.text_widget.tag_names(start):
          self.text_widget.tag_add("keyword", start, end)

  def save_file(self):
    if not self.file_path:
      initial_dir = self.app_instance.current_project_dir if self.app_instance and self.app_instance.current_project_dir else "/"
      self.file_path = filedialog.asksaveasfilename(
          initialdir=initial_dir,
          defaultextension=".txt",
          filetypes=[("All Files", "*.*"), ("Python Files", "*.py")],
      )
      if not self.file_path:
        return False

    try:
      content = self.text_widget.get("1.0", tk.END[:-1])
      with open(self.file_path, "w", encoding="utf-8") as f:
        f.write(content)
      self.title_label.config(text=os.path.basename(self.file_path))
      if self.app_instance and self.app_instance.current_project_dir:
        self.app_instance.populate_tree(self.app_instance.current_project_dir)
      return True
    except Exception as e:
      messagebox.showerror("Error", str(e))
      return False

  def save_and_close(self):
    if self.save_file():
      self.close_tab()

  def close_tab(self):
    if self.app_instance:
      self.app_instance.remove_tab(self)


class CodeStudioMe(tk.Tk):
  def __init__(self):
    super().__init__()
    self.title("CSU - CodeStudioUniversial")
    self.geometry("1000x650")
    self.configure(bg="#1e1e1e")

    try:
      self.iconbitmap("icon.ico")
    except Exception:
      pass

    self.current_project_dir = None
    self.open_tabs = {}

    self.create_widgets()
    self.bind_shortcuts()
    self.load_last_project()

  def create_widgets(self):
    style = ttk.Style()
    style.theme_use("clam")
    
    style.configure(".", background="#1e1e1e", foreground="#cccccc")
    style.configure("TPanedwindow", background="#1e1e1e")
    style.configure("TNotebook", background="#1e1e1e", borderwidth=0)
    style.configure("TNotebook.Tab", background="#2d2d2d", foreground="#cccccc", padding=[10, 4], borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", "#1e1e1e")], foreground=[("selected", "#ffffff")])
    
    style.configure("Treeview", background="#252526", foreground="#cccccc", fieldbackground="#252526", borderwidth=0)
    style.map("Treeview", background=[('selected', '#37373d')], foreground=[('selected', '#ffffff')])

    self.main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
    self.main_pane.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

    self.left_frame = tk.Frame(self.main_pane, bg="#252526")
    self.main_pane.add(self.left_frame, weight=1)

    self.buttons_frame = tk.Frame(self.left_frame, bg="#252526")
    self.buttons_frame.pack(fill=tk.X, padx=4, pady=4)
    self.buttons_frame.columnconfigure(0, weight=1)
    self.buttons_frame.columnconfigure(1, weight=1)

    btn_style = {"bg": "#333333", "fg": "#cccccc", "activebackground": "#3f3f46", "activeforeground": "#ffffff", "bd": 0, "relief": "flat", "pady": 6}

    self.btn_open_folder = tk.Button(self.buttons_frame, text="Open Folder", command=self.open_project_folder, **btn_style)
    self.btn_open_folder.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

    self.btn_terminal = tk.Button(self.buttons_frame, text="Terminal", command=self.open_terminal, **btn_style)
    self.btn_terminal.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)

    self.btn_new_file = tk.Button(self.buttons_frame, text="New File", command=self.create_new_file, **btn_style)
    self.btn_new_file.grid(row=1, column=0, sticky="nsew", padx=2, pady=2)

    self.btn_new_folder = tk.Button(self.buttons_frame, text="New Folder", command=self.create_new_folder, **btn_style)
    self.btn_new_folder.grid(row=1, column=1, sticky="nsew", padx=2, pady=2)

    self.tree = ttk.Treeview(self.left_frame, selectmode="browse")
    self.tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
    self.tree.bind("<Double-1>", self.on_tree_double_click)
    self.tree.bind("<Button-3>", self.show_context_menu)

    self.right_frame = tk.Frame(self.main_pane, bg="#1e1e1e")
    self.main_pane.add(self.right_frame, weight=4)

    self.notebook = ttk.Notebook(self.right_frame)
    self.notebook.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

    self.update_idletasks()
    try:
      self.main_pane.sashpos(0, 250)
    except Exception:
      pass

    self.protocol("WM_DELETE_WINDOW", self.on_closing)

  def bind_shortcuts(self):
    self.bind("<Control-n>", lambda e: self.new_file_tab())
    self.bind("<Control-t>", lambda e: self.open_terminal())

  def load_last_project(self):
    if os.path.exists(CONFIG_FILE):
      try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
          data = json.load(f)
          last_dir = data.get("last_project")
          if last_dir and os.path.exists(last_dir):
            self.current_project_dir = last_dir
            self.populate_tree(last_dir)
            return
      except:
        pass
    self.new_file_tab()

  def save_last_project(self, path):
    try:
      with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_project": path}, f)
    except:
      pass

  def open_project_folder(self):
    dir_path = filedialog.askdirectory()
    if dir_path:
      self.current_project_dir = dir_path
      self.save_last_project(dir_path)
      self.populate_tree(dir_path)

  def create_new_file(self):
    if not self.current_project_dir:
      messagebox.showerror("Error", "Please open a project folder first.")
      return
    file_name = simpledialog.askstring("New File", "Enter file name:")
    if file_name:
      full_path = os.path.join(self.current_project_dir, file_name)
      try:
        with open(full_path, "w", encoding="utf-8") as f:
          f.write("")
        self.populate_tree(self.current_project_dir)
        self.open_file_in_tab(full_path)
      except Exception as e:
        messagebox.showerror("Error", str(e))

  def create_new_folder(self):
    if not self.current_project_dir:
      messagebox.showerror("Error", "Please open a project folder first.")
      return
    folder_name = simpledialog.askstring("New Folder", "Enter folder name:")
    if folder_name:
      full_path = os.path.join(self.current_project_dir, folder_name)
      try:
        os.makedirs(full_path, exist_ok=True)
        self.populate_tree(self.current_project_dir)
      except Exception as e:
        messagebox.showerror("Error", str(e))

  def open_terminal(self):
    cwd = self.current_project_dir if self.current_project_dir else os.getcwd()
    try:
      subprocess.Popen(["start", "cmd.exe"], shell=True, cwd=cwd)
    except Exception as e:
      messagebox.showerror("Error", str(e))

  def populate_tree(self, path):
    for item in self.tree.get_children():
      self.tree.delete(item)
    root_node = self.tree.insert(
        "", "end", text=os.path.basename(path), open=True, values=[path]
    )
    self.load_directory_contents(root_node, path)

  def load_directory_contents(self, parent, path):
    try:
      for entry in sorted(os.listdir(path)):
        full_path = os.path.join(path, entry)
        if os.path.isdir(full_path):
          node = self.tree.insert(
              parent, "end", text=entry, values=[full_path], open=False
          )
          self.tree.insert(node, "end", text="Loading...")
        else:
          self.tree.insert(
              parent, "end", text=entry, values=[full_path], open=False
          )
    except PermissionError:
      pass

  def on_tree_double_click(self, event):
    selected_item = self.tree.focus()
    if not selected_item:
      return
    item_values = self.tree.item(selected_item, "values")
    if not item_values:
      return
    path = item_values[0]

    if os.path.isdir(path):
      children = self.tree.get_children(selected_item)
      if (
          len(children) == 1
          and self.tree.item(children[0], "text") == "Loading..."
      ):
        self.tree.delete(children[0])
        self.load_directory_contents(selected_item, path)
    elif os.path.isfile(path):
      self.open_file_in_tab(path)

  def show_context_menu(self, event):
    item = self.tree.identify_row(event.y)
    if item:
      self.tree.selection_set(item)
      menu = tk.Menu(self, tearoff=0, bg="#252526", fg="#cccccc")
      menu.add_command(label="Переименовать", command=lambda: self.rename_item(item))
      menu.add_command(label="Удалить", command=lambda: self.delete_item(item))
      menu.tk_popup(event.x_root, event.y_root)

  def rename_item(self, item):
    path = self.tree.item(item, "values")[0]
    old_name = os.path.basename(path)
    new_name = simpledialog.askstring("Переименовать", "Новое имя:", initialvalue=old_name)
    if new_name and new_name != old_name:
      dir_name = os.path.dirname(path)
      new_path = os.path.join(dir_name, new_name)
      try:
        os.rename(path, new_path)
        if self.current_project_dir:
          self.populate_tree(self.current_project_dir)
      except Exception as e:
        messagebox.showerror("Ошибка", str(e))

  def delete_item(self, item):
    path = self.tree.item(item, "values")[0]
    name = os.path.basename(path)
    if messagebox.askyesno("Удаление", f"Точно удалить '{name}'?"):
      try:
        if os.path.isdir(path):
          shutil.rmtree(path)
        else:
          os.remove(path)
        if self.current_project_dir:
          self.populate_tree(self.current_project_dir)
      except Exception as e:
        messagebox.showerror("Ошибка", str(e))

  def open_file_in_tab(self, file_path):
    for tab_id, editor in self.open_tabs.items():
      if editor.file_path == file_path:
        self.notebook.select(tab_id)
        return

    editor = CodeEditor(self.notebook, file_path=file_path, app_instance=self)
    self.notebook.add(editor, text=os.path.basename(file_path))
    self.notebook.select(editor)
    self.open_tabs[str(editor)] = editor

  def new_file_tab(self):
    editor = CodeEditor(self.notebook, file_path=None, app_instance=self)
    self.notebook.add(editor, text="Untitled")
    self.notebook.select(editor)
    self.open_tabs[str(editor)] = editor

  def remove_tab(self, editor):
    tab_key = str(editor)
    if tab_key in self.open_tabs:
      self.notebook.forget(editor)
      del self.open_tabs[tab_key]

  def on_closing(self):
    self.destroy()


if __name__ == "__main__":
  app = CodeStudioMe()
  app.mainloop()
