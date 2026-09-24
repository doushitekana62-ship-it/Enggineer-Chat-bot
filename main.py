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
        self.root.title("Engineer AI - Prototype")
        self.root.geometry("760x600")
        self.root.minsize(700, 520)

        self.db = DatabaseService()
        self.ollama = OllamaService()

        self.db_vars = {
            "host": tk.StringVar(value=config.DB_HOST),
            "port": tk.StringVar(value=str(config.DB_PORT)),
            "name": tk.StringVar(value=config.DB_NAME),
            "user": tk.StringVar(value=config.DB_USER),
            "password": tk.StringVar(value=config.DB_PASSWORD),
        }

        self._build_ui()
        self.refresh_status()

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)

        settings = ttk.Frame(notebook, padding=15)
        chat = ttk.Frame(notebook, padding=15)
        notebook.add(settings, text="Database Settings")
        notebook.add(chat, text="AI Chat")

        ttk.Label(
            settings,
            text="Engineering Database Connection",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            settings,
            text="Masukkan credential PostgreSQL kantor. Data disimpan lokal di file .env.",
            foreground="#555555",
        ).pack(anchor="w", pady=(4, 15))

        form = ttk.Frame(settings)
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

        buttons = ttk.Frame(settings)
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

        self.status_text = tk.Text(settings, height=12, wrap="word")
        self.status_text.pack(fill="both", expand=True, pady=(5, 0))
        self.status_text.configure(state="disabled")

        ttk.Label(
            chat,
            text="Engineering AI Chat",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            chat,
            text="Prototype query:",
            foreground="#555555",
        ).pack(anchor="w", pady=(4, 5))

        self.question = tk.Text(chat, height=5, wrap="word")
        self.question.pack(fill="x")

        ttk.Button(
            chat,
            text="Ask Llama 3.2 3B",
            command=self.ask_question,
        ).pack(anchor="w", pady=10)

        self.answer = tk.Text(chat, wrap="word")
        self.answer.pack(fill="both", expand=True)
        self.answer.configure(state="disabled")

    @staticmethod
    def _env_path() -> Path:
        base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        return base / ".env"

    def _write_status(self, text: str):
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", text)
        self.status_text.configure(state="disabled")

    def refresh_status(self):
        db = self.db.status()
        ollama = self.ollama.status()

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
                file.write("DEMO_MODE=false\\n")
                file.write(f"OLLAMA_URL={config.OLLAMA_URL}\\n")
                file.write(f"OLLAMA_MODEL={config.OLLAMA_MODEL}\\n")
                file.write(f"DB_HOST={config.DB_HOST}\\n")
                file.write(f"DB_PORT={config.DB_PORT}\\n")
                file.write(f"DB_NAME={config.DB_NAME}\\n")
                file.write(f"DB_USER={config.DB_USER}\\n")
                file.write(f"DB_PASSWORD={config.DB_PASSWORD}\\n")

            config.DEMO_MODE = False

            status = self.db.status()
            if status.get("connected"):
                messagebox.showinfo(
                    "Database Connected",
                    "PostgreSQL Engineering berhasil terhubung.",
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
            messagebox.showwarning("Question", "Masukkan pertanyaan.")
            return

        self.answer.configure(state="normal")
        self.answer.delete("1.0", "end")
        self.answer.insert("1.0", "Processing...")
        self.answer.configure(state="disabled")

        def worker():
            try:
                context = self.db.get_context(question)
                answer = self.ollama.chat(question, context)
                result = (
                    f"{answer}\n\n"
                    f"[Data source: {context.get('source')}]"
                )
            except Exception as exc:
                result = f"ERROR: {exc}"

            self.root.after(0, lambda: self._show_answer(result))

        threading.Thread(target=worker, daemon=True).start()

    def _show_answer(self, text: str):
        self.answer.configure(state="normal")
        self.answer.delete("1.0", "end")
        self.answer.insert("1.0", text)
        self.answer.configure(state="disabled")


if __name__ == "__main__":
    threading.Thread(target=start_api, daemon=True).start()

    root = tk.Tk()
    EngineerAIApp(root)
    root.mainloop()
