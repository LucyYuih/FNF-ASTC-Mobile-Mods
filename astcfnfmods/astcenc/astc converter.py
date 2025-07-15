import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image
import tempfile
import threading
import queue
import sys
import json
import math

# Lista de tamanhos de bloco suportados
BLOCK_SIZES = ['4x4','5x4','5x5','6x5','6x6','8x5','8x6','8x8','10x5','10x6','10x8','10x10','12x10','12x12']

class ASTCConverterApp:
    CONFIG_FILE = "astc_config.json"
    
    def __init__(self, root):
        self.root = root
        self.root.title("Conversor ASTC Turbo")
        self.root.geometry("720x650")
        
        # Variáveis
        self.input_folder = tk.StringVar()
        self.astcenc_path = tk.StringVar()
        self.block_size = tk.StringVar(value="Auto")
        self.quality = tk.StringVar(value="-fast")
        self.running = False
        self.cancelled = False
        self.queue = queue.Queue()
        self.total_images = 0
        self.completed_images = 0
        
        self.load_config()
        
        frame = ttk.Frame(root, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Pasta de imagens
        ttk.Label(frame, text="Pasta com Imagens:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.input_folder, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(frame, text="Procurar", command=self.browse_folder).grid(row=0, column=2)
        
        # Executável astcenc
        ttk.Label(frame, text="Caminho do astcenc.exe:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.astcenc_path, width=50).grid(row=1, column=1, padx=5)
        ttk.Button(frame, text="Procurar", command=self.browse_astcenc).grid(row=1, column=2)
        
        # Tamanho de bloco
        ttk.Label(frame, text="Tamanho do Bloco:").grid(row=2, column=0, sticky="w", pady=5)
        block_combo = ttk.Combobox(
            frame,
            textvariable=self.block_size,
            width=12,
            values=['Auto'] + BLOCK_SIZES
        )
        block_combo.current(0)
        block_combo.grid(row=2, column=1, sticky="w", padx=5)
        
        # Qualidade
        ttk.Label(frame, text="Qualidade:").grid(row=3, column=0, sticky="w", pady=5)
        quality_combo = ttk.Combobox(
            frame,
            textvariable=self.quality,
            width=10,
            values=('-fast','-medium','-thorough','-exhaustive')
        )
        quality_combo.current(0)
        quality_combo.grid(row=3, column=1, sticky="w", padx=5)
        
        # Botões
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=15)
        self.convert_btn = ttk.Button(btn_frame, text="Converter", command=self.toggle_conversion, width=15)
        self.convert_btn.pack(side=tk.LEFT, padx=5)
        self.status_label = ttk.Label(btn_frame, text="Pronto")
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Barra de progresso
        self.progress = ttk.Progressbar(frame, orient="horizontal", length=400, mode="determinate")
        self.progress.grid(row=5, column=0, columnspan=3, pady=10, sticky="we")
        
        # Log
        log_frame = ttk.Frame(frame)
        log_frame.grid(row=6, column=0, columnspan=3, pady=10, sticky="nsew")
        ttk.Label(log_frame, text="Log de Execução:").pack(anchor="w")
        self.log = tk.Text(log_frame, height=12, width=80)
        self.log.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log['yscrollcommand'] = scrollbar.set

        self.root.after(100, self.process_queue)

    def load_config(self):
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, 'r') as f:
                    cfg = json.load(f)
                    self.input_folder.set(cfg.get('input_folder', ''))
                    self.astcenc_path.set(cfg.get('astcenc_path', ''))
                    self.block_size.set(cfg.get('block_size', 'Auto'))
                    self.quality.set(cfg.get('quality', '-fast'))
        except:
            pass

    def save_config(self):
        cfg = {
            'input_folder': self.input_folder.get(),
            'astcenc_path': self.astcenc_path.get(),
            'block_size': self.block_size.get(),
            'quality': self.quality.get()
        }
        with open(self.CONFIG_FILE, 'w') as f:
            json.dump(cfg, f)

    def browse_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.input_folder.set(d)
            self.save_config()

    def browse_astcenc(self):
        f = filedialog.askopenfilename(
            title="Selecione o executável astcenc",
            filetypes=[("Executável", "*.exe"), ("Todos", "*.*")]
        )
        if f:
            self.astcenc_path.set(f)
            self.save_config()

    def log_message(self, msg):
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

    def choose_best_block(self, width, height):
        # Seleciona o tamanho que minimiza pixel padding
        best = None
        min_pad = None
        for b in BLOCK_SIZES:
            bx, by = map(int, b.split('x'))
            pad_w = (math.ceil(width/bx)*bx - width)
            pad_h = (math.ceil(height/by)*by - height)
            pad = pad_w * by + pad_h * bx  # estimativa de overhead
            if min_pad is None or pad < min_pad:
                min_pad = pad
                best = (bx, by)
        return best

    def convert_image(self, path):
        tmp = None
        try:
            astcenc = self.astcenc_path.get()
            if not os.path.exists(astcenc):
                return "ERRO: astcenc inválido!"
            out = os.path.splitext(path)[0] + ".astc"
            if os.path.exists(out):
                return f"Pulando: {os.path.basename(path)}"

            # determina block size
            with Image.open(path) as img:
                w, h = img.size
            if self.block_size.get() == 'Auto':
                bx, by = self.choose_best_block(w, h)
            else:
                bx, by = map(int, self.block_size.get().split('x'))

            with Image.open(path) as img:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                img = self.pad_image_to_block(img, bx, by)
                base_name = os.path.splitext(os.path.basename(path))[0] + ".png"
                tmp = os.path.join(tempfile.gettempdir(), base_name)
                img.save(tmp, "PNG", compress_level=1)

            cmd = [
                astcenc,
                "-cl",
                tmp,
                out,
                f"{bx}x{by}",
                self.quality.get()
            ]
            proc_kwargs = {}
            if sys.platform == "win32":
                proc_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

            res = subprocess.run(cmd, capture_output=True, text=True, **proc_kwargs)
            if res.returncode != 0:
                err = res.stderr.strip() or "Erro desconhecido"
                return f"ERRO em {os.path.basename(path)}: {err}"

            os.remove(path)
            return f"Convertido ({bx}x{by}): {os.path.basename(path)}"
        except Exception as e:
            return f"ERRO em {os.path.basename(path)}: {e}"
        finally:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)

    def pad_image_to_block(self, img, bx, by):
        w, h = img.size
        nw = math.ceil(w/bx)*bx
        nh = math.ceil(h/by)*by
        if nw == w and nh == h:
            return img
        new = Image.new("RGBA", (nw,nh), (0,0,0,0))
        new.paste(img, (0,0))
        return new

    def worker(self):
        while not self.cancelled:
            try:
                img = self.work_queue.get_nowait()
                self.queue.put(("log", self.convert_image(img)))
                self.queue.put(("progress",))
                self.work_queue.task_done()
            except queue.Empty:
                break

    def run_conversion(self):
        inp = self.input_folder.get()
        astc = self.astcenc_path.get()
        if not os.path.isdir(inp): self.queue.put(("log","ERRO: pasta inválida!")); return
        if not os.path.exists(astc): self.queue.put(("log","ERRO: astcenc inválido!")); return

        exts = ('.png','.jpg','.jpeg','.bmp','.tga','.tif','.tiff','.webp')
        imgs = [os.path.join(r,f)
                for r,_,fs in os.walk(inp) for f in fs
                if f.lower().endswith(exts)]
        if not imgs:
            self.queue.put(("log","Nenhuma imagem encontrada!"))
            return

        self.total_images = len(imgs)
        self.completed_images = 0
        self.queue.put(("progress_reset", self.total_images))
        self.queue.put(("log", f"Encontradas {self.total_images} imagens."))
        self.queue.put(("log", f"Usando astcenc em: {astc}"))

        self.work_queue = queue.Queue()
        for i in imgs:
            self.work_queue.put(i)

        threads = min(os.cpu_count() or 1, 4)
        self.queue.put(("log", f"Usando {threads} threads..."))
        for _ in range(threads):
            t = threading.Thread(target=self.worker, daemon=True)
            t.start()

        self.work_queue.join()
        if not self.cancelled:
            self.queue.put(("log","\nConversão concluída!"))
        else:
            self.queue.put(("log","Conversão cancelada!"))
        self.queue.put(("done",))

    def process_queue(self):
        try:
            while True:
                task = self.queue.get_nowait()
                if task[0] == "log":
                    self.log_message(task[1])
                elif task[0] == "progress_reset":
                    self.progress["maximum"] = task[1]
                    self.progress["value"] = 0
                    self.status_label.config(text=f"Convertendo: 0/{task[1]}")
                elif task[0] == "progress":
                    self.completed_images += 1
                    self.progress["value"] = self.completed_images
                    self.status_label.config(text=f"Convertendo: {self.completed_images}/{self.total_images}")
                elif task[0] == "done":
                    self.running = False
                    self.cancelled = False
                    self.convert_btn.config(text="Converter", state="normal")
                    self.status_label.config(text="Pronto")
        except queue.Empty:
            pass
        self.root.after(100, self.process_queue)

    def toggle_conversion(self):
        if not self.running:
            self.running = True
            self.cancelled = False
            self.convert_btn.config(text="Cancelar")
            self.log.delete(1.0, tk.END)
            threading.Thread(target=self.run_conversion, daemon=True).start()
        else:
            self.cancelled = True
            self.convert_btn.config(state="disabled")
            self.status_label.config(text="Cancelando...")
            self.log_message("Cancelando...")

if __name__ == "__main__":
    root = tk.Tk()
    app = ASTCConverterApp(root)
    root.mainloop()
