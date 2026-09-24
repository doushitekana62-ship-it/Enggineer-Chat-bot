import threading
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import uvicorn

from app import config
from app.ai.ollama import OllamaService
from app.api.server import app
from app.database.service import DatabaseService


def start_api():
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="warning",
    )


class EngineerAIApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Engineer AI")
        self.root.geometry("900x680")
        self.root.minsize(760, 560)

        self.db = DatabaseService()
        self.ollama = OllamaService()
        self.chat_widgets = []

        self.db_vars = {
            "host": tk.StringVar(value=config.DB_HOST),
            "port": tk.StringVar(value=str(config.DB_PORT)),
            "name": tk.StringVar(value=config.DB_NAME),
            "user": tk.StringVar(value=config.DB_USER),
            "password": tk.StringVar(value=config.DB_PASSWORD),
        }

        self._build_ui()
        self.refresh_status()

    @staticmethod
    def _env_path() -> Path:
        base = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent
        )
        return base / ".env"

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        settings = ttk.Frame(notebook, padding=15)
        chat = ttk.Frame(notebook, padding=12)
        notebook.add(chat, text="Chat")
        notebook.add(settings, text="Database Settings")

        self._build_chat(chat)
        self._build_settings(settings)

    def _build_chat(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill="x", pady=(0, 8))

        ttk.Label(
            header,
            text="Engineering Assistant",
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")

        self.connection_label = ttk.Label(
            header,
            text="Checking connection...",
            foreground="#666666",
        )
        self.connection_label.pack(side="right", pady=4)

        chat_box = ttk.Frame(parent)
        chat_box.pack(fill="both", expand=True)

        self.chat_canvas = tk.Canvas(
            chat_box,
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(
            chat_box,
            orient="vertical",
            command=self.chat_canvas.yview,
        )
        self.chat_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.chat_canvas.pack(side="left", fill="both", expand=True)

        self.chat_frame = tk.Frame(self.chat_canvas)
        self.chat_window = self.chat_canvas.create_window(
            (0, 0),
            window=self.chat_frame,
            anchor="nw",
        )

        self.chat_frame.bind(
            "<Configure>",
            lambda event: self.chat_canvas.configure(
                scrollregion=self.chat_canvas.bbox("all")
            ),
        )
        self.chat_canvas.bind(
            "<Configure>",
            lambda event: self.chat_canvas.itemconfigure(
                self.chat_window,
                width=event.width,
            ),
        )

        self._add_message(
            "assistant",
            "Halo. Saya Engineer AI. Silakan tanyakan data Engineering.",
        )

        composer = ttk.Frame(parent)
        composer.pack(fill="x", pady=(10, 0))

        self.question = tk.Text(
            composer,
            height=3,
            wrap="word",
            font=("Segoe UI", 10),
        )
        self.question.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.question.bind("<Control-Return>", lambda event: self.ask_question())

        ttk.Button(
            composer,
            text="Kirim",
            command=self.ask_question,
            width=10,
        ).pack(side="right", fill="y")

    def _build_settings(self, parent):
        ttk.Label(
            parent,
            text="Engineering Database Connection",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            parent,
            text="Masukkan credential PostgreSQL. Konfigurasi disimpan secara lokal.",
            foreground="#555555",
        ).pack(anchor="w", pady=(4, 15))

        form = ttk.Frame(parent)
        form.pack(fill="x")

        labels = [
            ("Host", "host"),
            ("Port", "port"),
            ("Database", "name"),
            ("Username", "user"),
            ("Password", "password"),
        ]

        for row, (label, key) in enumerate(labels):
            ttk.Label(form, text=label, width=14).grid(
                row=row, column=0, sticky="w", pady=5
            )
            entry = ttk.Entry(form, textvariable=self.db_vars[key], width=55)
            if key == "password":
                entry.configure(show="*")
            entry.grid(row=row, column=1, sticky="ew", pady=5)

        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(parent)
        buttons.pack(anchor="w", pady=15)

        ttk.Button(
            buttons,
            text="Save & Test Database",
            command=self.save_and_test,
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            buttons,
            text="Refresh Status",
            command=self.refresh_status,
        ).pack(side="left")

        self.status_text = tk.Text(parent, height=12, wrap="word")
        self.status_text.pack(fill="both", expand=True, pady=(5, 0))
        self.status_text.configure(state="disabled")

    def _add_message(self, role: str, text: str):
        row = tk.Frame(self.chat_frame)
        row.pack(fill="x", padx=8, pady=5)

        if role == "user":
            bubble = tk.Label(
                row,
                text=text,
                justify="left",
                anchor="w",
                wraplength=620,
                padx=12,
                pady=8,
                bg="#E8F0FE",
                fg="#202124",
                font=("Segoe UI", 10),
            )
            bubble.pack(side="right", padx=(100, 0))
        else:
            bubble = tk.Label(
                row,
                text=text,
                justify="left",
                anchor="w",
                wraplength=620,
                padx=12,
                pady=8,
                bg="#F1F3F4",
                fg="#202124",
                font=("Segoe UI", 10),
            )
            bubble.pack(side="left", padx=(0, 100))

        self.chat_widgets.append(row)
        self.root.after_idle(
            lambda: self.chat_canvas.yview_moveto(1.0)
        )

    def _add_status_message(self, source: str):
        label = tk.Label(
            self.chat_frame,
            text=f"Sumber data: {source}",
            anchor="w",
            fg="#777777",
            font=("Segoe UI", 8),
        )
        label.pack(fill="x", padx=14, pady=(0, 5))
        self.chat_widgets.append(label)

    def _write_status(self, text: str):
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", text)
        self.status_text.configure(state="disabled")

    def refresh_status(self):
        db = self.db.status()
        ollama = self.ollama.status()

        self.connection_label.configure(
            text=(
                "Database terhubung"
                if db.get("connected")
                else "Database belum terhubung"
            )
        )

        text = (
            f"MODE: {'DEMO' if config.DEMO_MODE else 'LIVE'}\n\n"
            f"DATABASE\n"
            f"  Connected : {db.get('connected')}\n"
            f"  Mode      : {db.get('mode')}\n"
            f"  Message   : {db.get('message')}\n\n"
            f"OLLAMA\n"
            f"  Connected : {ollama.get('connected')}\n"
            f"  Model     : {ollama.get('model')}\n"
            f"  Available : {ollama.get('model_available')}\n"
        )

        self._write_status(text)

    def save_and_test(self):
        try:
            config.DB_HOST = self.db_vars["host"].get().strip()
            config.DB_PORT = int(self.db_vars["port"].get().strip() or "5432")
            config.DB_NAME = self.db_vars["name"].get().strip()
            config.DB_USER = self.db_vars["user"].get().strip()
            config.DB_PASSWORD = self.db_vars["password"].get()

            with open(self._env_path(), "w", encoding="utf-8") as file:
                file.write("DEMO_MODE=false\n")
                file.write(f"OLLAMA_URL={config.OLLAMA_URL}\n")
                file.write(f"OLLAMA_MODEL={config.OLLAMA_MODEL}\n")
                file.write(f"DB_HOST={config.DB_HOST}\n")
                file.write(f"DB_PORT={config.DB_PORT}\n")
                file.write(f"DB_NAME={config.DB_NAME}\n")
                file.write(f"DB_USER={config.DB_USER}\n")
                file.write(f"DB_PASSWORD={config.DB_PASSWORD}\n")

            config.DEMO_MODE = False

            status = self.db.status()
            if status.get("connected"):
                messagebox.showinfo(
                    "Database Connected",
                    "PostgreSQL berhasil terhubung.",
                )
            else:
                messagebox.showerror(
                    "Database Connection Failed",
                    status.get("message", "Unknown error"),
                )

            self.refresh_status()

        except ValueError:
            messagebox.showerror("Invalid Port", "Port harus berupa angka.")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def ask_question(self):
        question = self.question.get("1.0", "end").strip()
        if not question:
            return

        self.question.delete("1.0", "end")
        self._add_message("user", question)
        self._add_message("assistant", "Sedang mencari informasi...")
        pending_row = self.chat_widgets[-1]

        def worker():
            try:
                context = self.db.get_context(question)
                answer = self.ollama.chat(question, context)
                result = answer
                source = context.get("source", "unknown")
            except Exception as exc:
                result = f"Terjadi kesalahan: {exc}"
                source = "error"

            self.root.after(
                0,
                lambda: self._replace_pending(
                    pending_row, result, source
                ),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _replace_pending(self, pending_row, answer: str, source: str):
        pending_row.destroy()
        if pending_row in self.chat_widgets:
            self.chat_widgets.remove(pending_row)
        self._add_message("assistant", answer)
        self._add_status_message(source)

    def clear_chat(self):
        for widget in self.chat_widgets:
            widget.destroy()
        self.chat_widgets.clear()
        self._add_message(
            "assistant",
            "Percakapan baru dimulai. Silakan tanyakan data Engineering.",
        )


if __name__ == "__main__":
    threading.Thread(target=start_api, daemon=True).start()

    root = tk.Tk()
    EngineerAIApp(root)
    root.mainloop()
