import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image
import tempfile
import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor

CONFIG_FILE = os.path.join(os.path.expanduser('~'), 'astc_config.json')
BLOCK_SIZES = ['4x4','5x4','5x5','6x5','6x6','8x5','8x6','8x8','10x5','10x6','10x8','10x10','12x10','12x12']
IGNORE_PATH = os.path.join('images', 'freeplay', 'icons')  # Caminho a ser ignorado

class ASTCConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ASTC Converter Pydroid3 + Tkinter")
        self.root.geometry("600x550")
        self.load_config()

        self.input_folder = tk.StringVar(value=self.cfg.get('input_folder', ''))
        self.astcenc_path = tk.StringVar(value=self.cfg.get('astcenc_path', ''))
        self.block_size = tk.StringVar(value=self.cfg.get('block_size', '8x8'))
        self.quality = tk.StringVar(value=self.cfg.get('quality', '-fast'))
        self.auto = tk.BooleanVar(value=(self.block_size.get().lower() == 'auto'))
        self.cancel_event = threading.Event()

        frame = ttk.Frame(root, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Pasta de Imagens:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.input_folder, width=40).grid(row=0, column=1)
        ttk.Button(frame, text="Procurar", command=self.browse_folder).grid(row=0, column=2)

        ttk.Label(frame, text="astcenc Path:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.astcenc_path, width=40).grid(row=1, column=1)
        ttk.Button(frame, text="Procurar", command=self.browse_astcenc).grid(row=1, column=2)

        ttk.Label(frame, text="Tamanho do Bloco:").grid(row=2, column=0, sticky="w", pady=5)
        block_combo = ttk.Combobox(frame, textvariable=self.block_size, width=10, values=['Auto'] + BLOCK_SIZES)
        block_combo.grid(row=2, column=1, sticky="w")
        block_combo.bind('<<ComboboxSelected>>', lambda e: self.auto.set(self.block_size.get().lower() == 'auto'))

        ttk.Label(frame, text="Qualidade:").grid(row=3, column=0, sticky="w", pady=5)
        quality_combo = ttk.Combobox(frame, textvariable=self.quality, width=10, values=['-fast', '-medium', '-thorough', '-exhaustive'])
        quality_combo.grid(row=3, column=1, sticky="w")

        self.btn_convert = ttk.Button(frame, text="Converter", command=self.start_conversion)
        self.btn_convert.grid(row=4, column=0, columnspan=1, pady=10)
        self.btn_cancel = ttk.Button(frame, text="Cancelar", command=self.cancel_conversion, state=tk.DISABLED)
        self.btn_cancel.grid(row=4, column=1, columnspan=1)

        self.progress = ttk.Progressbar(frame, orient="horizontal", mode="determinate")
        self.progress.grid(row=5, column=0, columnspan=3, sticky="we", pady=5)

        ttk.Label(frame, text="Log:").grid(row=6, column=0, sticky="w")
        self.log = tk.Text(frame, height=10)
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew")

        frame.rowconfigure(7, weight=1)
        frame.columnconfigure(1, weight=1)

    def load_config(self):
        try:
            with open(CONFIG_FILE, 'r') as f:
                self.cfg = json.load(f)
        except:
            self.cfg = {}

    def save_config(self):
        cfg = {
            'input_folder': self.input_folder.get(),
            'astcenc_path': self.astcenc_path.get(),
            'block_size': self.block_size.get(),
            'quality': self.quality.get()
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f)

    def browse_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.input_folder.set(d)

    def browse_astcenc(self):
        f = filedialog.askopenfilename(filetypes=[('Executável', '*.exe'), ('Todos', '*.*')])
        if f:
            self.astcenc_path.set(f)

    def log_message(self, msg):
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

    def choose_best_block(self, w, h, file_size):
        best, best_diff = None, None
        for b in BLOCK_SIZES:
            bx, by = map(int, b.split('x'))
            blocks = math.ceil(w/bx) * math.ceil(h/by)
            est_size = blocks * 16
            diff = abs(est_size - file_size)
            if best_diff is None or diff < best_diff:
                best_diff, best = diff, (bx, by)
        return best

    def pad_image(self, img, bx, by):
        w, h = img.size
        nw, nh = math.ceil(w / bx) * bx, math.ceil(h / by) * by
        if (nw, nh) == (w, h):
            return img
        new = Image.new('RGBA', (nw, nh), (0, 0, 0, 0))
        new.paste(img, (0, 0))
        return new

    def convert_one(self, path, done_callback):
        if self.cancel_event.is_set():
            self.root.after(0, lambda: self.log_message(f"Cancelado: {path}"))
            self.root.after(0, done_callback)
            return
        try:
            norm = path.replace('\\', '/').lower()
            if IGNORE_PATH.replace('\\', '/').lower() in norm:
                self.root.after(0, lambda: self.log_message(f"Ignorado (padrão): {path}"))
                self.root.after(0, done_callback)
                return

            astcenc = self.astcenc_path.get()
            out = os.path.splitext(path)[0] + '.astc'
            if os.path.exists(out):
                self.root.after(0, lambda: self.log_message(f"Pulando: {path}"))
                self.root.after(0, done_callback)
                return

            file_size = os.path.getsize(path)
            with Image.open(path) as img:
                w, h = img.size
                if self.auto.get():
                    bx, by = self.choose_best_block(w, h, file_size)
                else:
                    bx, by = map(int, self.block_size.get().split('x'))
                img = img.convert('RGBA')
                img = self.pad_image(img, bx, by)
                tmp = os.path.join(tempfile.gettempdir(), os.path.basename(path) + '.png')
                img.save(tmp, 'PNG', compress_level=1)

            if self.cancel_event.is_set():
                os.remove(tmp)
                self.root.after(0, lambda: self.log_message(f"Cancelado: {path}"))
                self.root.after(0, done_callback)
                return

            cmd = [astcenc, '-cl', tmp, out, f'{bx}x{by}', self.quality.get()]
            res = subprocess.run(cmd, capture_output=True, text=True)
            try: os.remove(tmp)
            except: pass

            if res.returncode != 0:
                self.root.after(0, lambda: self.log_message(f"ERRO em {os.path.basename(path)}: {res.stderr.strip()}"))
            else:
                os.remove(path)
                self.root.after(0, lambda: self.log_message(f"Convertido ({bx}x{by}): {path}"))
        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"Erro: {e}"))
        finally:
            self.root.after(0, done_callback)

    def start_conversion(self):
        inp = self.input_folder.get()
        astc = self.astcenc_path.get()
        if not os.path.isdir(inp) or not os.path.isfile(astc):
            messagebox.showerror("Erro", "Verifique a pasta e o caminho do astcenc")
            return

        self.save_config()
        self.cancel_event.clear()
        self.btn_convert.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL)

        img_files = [
            os.path.join(r, f)
            for r, _, fs in os.walk(inp)
            for f in fs
            if f.lower().endswith(('.png', '.jpg', '.jpeg',
                                    '.bmp', '.tga', '.tif', '.tiff', '.webp'))
        ]

        total = len(img_files)
        if total == 0:
            messagebox.showinfo("Nada encontrado", "Nenhuma imagem válida encontrada.")
            self.btn_convert.config(state=tk.NORMAL)
            self.btn_cancel.config(state=tk.DISABLED)
            return

        self.progress['maximum'] = total
        self.progress['value'] = 0
        self.log.delete(1.0, tk.END)

        counter = {'done': 0}
        
        def done_callback():
            counter['done'] += 1
            self.progress['value'] = counter['done']
            if counter['done'] >= total:
                self.finish_conversion()

        executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 16)
        for path in img_files:
            executor.submit(self.convert_one, path, done_callback)

    def cancel_conversion(self):
        self.cancel_event.set()
        self.btn_cancel.config(state=tk.DISABLED)
        self.log_message("Cancelamento solicitado...")

    def finish_conversion(self):
        self.btn_convert.config(state=tk.NORMAL)
        self.btn_cancel.config(state=tk.DISABLED)
        if self.cancel_event.is_set():
            messagebox.showinfo("Cancelado", "Conversão foi cancelada pelo usuário.")
        else:
            messagebox.showinfo("Pronto", "Conversão concluída!")

if __name__ == '__main__':
    root = tk.Tk()
    app = ASTCConverterGUI(root)
    root.mainloop()
