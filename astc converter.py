import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import tempfile
import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor

CONFIG_FILE = os.path.join(os.path.expanduser('~'), 'astc_config.json')
BLOCK_SIZES = ['4x4','5x4','5x5','6x5','6x6','8x5','8x6','8x8','10x5','10x6','10x8','10x10','12x10','12x12']
IGNORE_PATH = os.path.join('images', 'freeplay', 'icons')
PIXEL_FOLDER_NAME = 'pixel'
WEEK6_FOLDER_NAME = 'week6'
PIXEL_ART_THRESHOLD = (10240, 10240)
MIN_SELECT_SIZE = (256, 256)
THUMB_SIZE = (128, 128)

class ASTCConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ASTC Converter com Seleção")
        self.root.geometry("750x750")
        self.load_config()

        self.input_folder = tk.StringVar(value=self.cfg.get('input_folder', ''))
        self.astcenc_path = tk.StringVar(value=self.cfg.get('astcenc_path', ''))
        self.block_size = tk.StringVar(value=self.cfg.get('block_size', '8x8'))
        self.quality = tk.StringVar(value=self.cfg.get('quality', '-fast'))
        self.auto = tk.BooleanVar(value=(self.block_size.get().lower() == 'auto'))
        self.cancel_event = threading.Event()
        self.selected_images = []

        self.build_main_ui()

    def build_main_ui(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        # Inputs
        ttk.Label(frame, text="Pasta de Imagens:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.input_folder, width=40).grid(row=0, column=1)
        ttk.Button(frame, text="Procurar", command=self.browse_folder).grid(row=0, column=2)

        ttk.Label(frame, text="astcenc Path:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.astcenc_path, width=40).grid(row=1, column=1)
        ttk.Button(frame, text="Procurar", command=self.browse_astcenc).grid(row=1, column=2)

        # Options
        ttk.Label(frame, text="Tamanho do Bloco:").grid(row=2, column=0, sticky="w", pady=5)
        block_combo = ttk.Combobox(frame, textvariable=self.block_size, width=10, values=['Auto'] + BLOCK_SIZES)
        block_combo.grid(row=2, column=1, sticky="w")
        block_combo.bind('<<ComboboxSelected>>', lambda e: self.auto.set(self.block_size.get().lower() == 'auto'))

        ttk.Label(frame, text="Qualidade:").grid(row=3, column=0, sticky="w", pady=5)
        quality_combo = ttk.Combobox(frame, textvariable=self.quality, width=10,
                                     values=['-fast', '-medium', '-thorough', '-exhaustive'])
        quality_combo.grid(row=3, column=1, sticky="w")

        # Buttons
        ttk.Button(frame, text="Selecionar Pixel Art", command=self.open_selection_window).grid(row=4, column=0, pady=10)
        self.btn_convert = ttk.Button(frame, text="Converter", command=self.start_conversion)
        self.btn_convert.grid(row=4, column=1, pady=10)
        self.btn_cancel = ttk.Button(frame, text="Cancelar", command=self.cancel_conversion, state=tk.DISABLED)
        self.btn_cancel.grid(row=4, column=2, pady=10)

        # Progress and log
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
        nw, nh = math.ceil(w/bx)*bx, math.ceil(h/by)*by
        if (nw, nh) == (w, h): return img
        new = Image.new('RGBA', (nw, nh), (0, 0, 0, 0))
        new.paste(img, (0, 0))
        return new

    def scan_small(self):
        small = []
        for r, _, files in os.walk(self.input_folder.get()):
            bn = os.path.basename(r).lower()
            if bn in (PIXEL_FOLDER_NAME, WEEK6_FOLDER_NAME): continue
            for f in files:
                if f.lower().endswith(('.png','.jpg','.jpeg','.bmp','.tga','.tif','.tiff','.webp')):
                    p=os.path.join(r,f); norm=p.replace('\\','/').lower()
                    if IGNORE_PATH.replace('\\','/').lower() in norm: continue
                    try:
                        with Image.open(p) as im: w,h=im.size
                    except: continue
                    if w<=PIXEL_ART_THRESHOLD[0] and h<=PIXEL_ART_THRESHOLD[1]: small.append({'path':p,'size':(w,h)})
        return small

    def scan_all(self):
        all_imgs=[]
        for r,_,files in os.walk(self.input_folder.get()):
            bn=os.path.basename(r).lower()
            if bn in (PIXEL_FOLDER_NAME,WEEK6_FOLDER_NAME): continue
            for f in files:
                if f.lower().endswith(('.png','.jpg','.jpeg','.bmp','.tga','.tif','.tiff','.webp')):
                    p=os.path.join(r,f); norm=p.replace('\\','/').lower()
                    if IGNORE_PATH.replace('\\','/').lower() in norm: continue
                    all_imgs.append(p)
        return all_imgs

    def open_selection_window(self):
        small = self.scan_small()
        if not small:
            messagebox.showinfo("Nada", "Nenhuma pixel art encontrada.")
            return
        sel = tk.Toplevel(self.root)
        sel.title("Seleção Pixel Art")
        sel.geometry("800x600")

        canvas = tk.Canvas(sel)
        vsb = ttk.Scrollbar(sel, orient='vertical', command=canvas.yview)
        hsb = ttk.Scrollbar(sel, orient='horizontal', command=canvas.xview)
        frame = tk.Frame(canvas)
        frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=frame, anchor='nw')
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        canvas.pack(fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')

        self.vars = {}
        cols = 4

        for idx, info in enumerate(small):
            row, col = divmod(idx, cols)
            p = info['path']
            w, h = info['size']
            default = not (w < MIN_SELECT_SIZE[0] and h < MIN_SELECT_SIZE[1])
            var = tk.BooleanVar(value=default)

            try:
                im = Image.open(p)
                im.thumbnail(THUMB_SIZE)
                photo = ImageTk.PhotoImage(im)
            except:
                continue

            lbl = ttk.Label(frame, image=photo)
            lbl.image = photo
            lbl.grid(row=row*2, column=col, padx=5, pady=5)

            cb = ttk.Checkbutton(frame, text=f"{os.path.relpath(p, self.input_folder.get())} ({w}x{h})", variable=var)
            cb.grid(row=row*2+1, column=col, sticky='w')
            self.vars[p] = var

        ttk.Button(sel, text="Confirmar", command=lambda: self.confirm_selection(sel)).pack(pady=5)

    def confirm_selection(self, win):
        self.selected_images = [p for p, v in self.vars.items() if v.get()]
        win.destroy()
        self.log_message(f"{len(self.selected_images)} pixel art selecionadas.")

    def start_conversion(self):
        all_imgs = self.scan_all()
        small_paths = [i['path'] for i in self.scan_small()]
        large = [p for p in all_imgs if p not in small_paths]
        to_convert = self.selected_images + large

        if not to_convert:
            messagebox.showwarning("Nada", "Nenhuma imagem para converter.")
            return

        self.save_config()
        self.cancel_event.clear()
        self.btn_convert.config(state='disabled')
        self.btn_cancel.config(state='normal')
        self.progress['maximum'] = len(to_convert)
        self.progress['value'] = 0
        self.log.delete('1.0', tk.END)

        done = {'n': 0}

        def cb():
            done['n'] += 1
            self.progress['value'] = done['n']
            if done['n'] >= len(to_convert):
                self.finish_conversion()

        exec = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)
        for p in to_convert:
            exec.submit(self.convert_one, p, cb)

    def convert_one(self, path, callback):
        if self.cancel_event.is_set():
            self.root.after(0, lambda: self.log_message(f"Cancelado: {path}"))
            self.root.after(0, callback)
            return

        out = os.path.splitext(path)[0] + '.astc'
        try:
            size = os.path.getsize(path)
            with Image.open(path) as im:
                w, h = im.size
                im = im.convert('RGBA')
            bx, by = (self.choose_best_block(w, h, size) if self.auto.get() else map(int, self.block_size.get().split('x')))
            im = self.pad_image(im, bx, by)
            tmp = os.path.join(tempfile.gettempdir(), os.path.basename(path) + '.png')
            im.save(tmp, 'PNG', compress_level=1)
            if self.cancel_event.is_set():
                os.remove(tmp)
                self.root.after(0, lambda: self.log_message(f"Cancelado: {path}"))
                self.root.after(0, callback)
                return
            res = subprocess.run([self.astcenc_path.get(), '-cl', tmp, out, f'{bx}x{by}', self.quality.get()], capture_output=True, text=True)
            os.remove(tmp)
            if res.returncode != 0:
                self.root.after(0, lambda: self.log_message(f"ERRO em {os.path.basename(path)}: {res.stderr.strip()}"))
            else:
                os.remove(path)
                self.root.after(0, lambda: self.log_message(f"Convertido: {path}"))
        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"Erro: {e}"))
        finally:
            self.root.after(0, callback)

    def cancel_conversion(self):
        self.cancel_event.set()
        self.btn_cancel.config(state='disabled')
        self.log_message("Cancelando...")

    def finish_conversion(self):
        self.btn_convert.config(state='normal')
        self.btn_cancel.config(state='disabled')
        messagebox.showinfo("Pronto", "Conversão concluída!" if not self.cancel_event.is_set() else "Cancelado pelo usuário.")

if __name__ == '__main__':
    root = tk.Tk()
    app = ASTCConverterGUI(root)
    root.mainloop()