import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image
import tempfile
import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Tentar importar ttkbootstrap, caso contrário, usar ttk padrão
try:
    from ttkbootstrap import Style
    ttk_style_available = True
except ImportError:
    ttk_style_available = False

CONFIG_FILE = os.path.join(os.path.expanduser("~"), "astc_config.json")
BLOCK_SIZES = ["4x4","5x4","5x5","6x5","6x6","8x5","8x6","8x8","10x5","10x6","10x8","10x10","12x10","12x12"]
IGNORE_PATH = os.path.join("images", "freeplay", "icons")  # Caminho a ser ignorado

class ASTCConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ASTC Converter Pydroid3 + Tkinter")
        self.root.geometry("600x550")
        self.root.resizable(True, True)
        self.load_config()

        if ttk_style_available:
            self.style = Style(theme=self.cfg.get("theme", "darkly")) # Tema padrão: darkly
            self.root.tk_setPalette(background=self.style.colors.bg)
        else:
            self.style = None

        self.input_folder = tk.StringVar(value=self.cfg.get("input_folder", ""))
        self.astcenc_path = tk.StringVar(value=self.cfg.get("astcenc_path", ""))
        self.block_size = tk.StringVar(value=self.cfg.get("block_size", "8x8"))
        self.quality = tk.StringVar(value=self.cfg.get("quality", "-fast"))
        self.auto = tk.BooleanVar(value=(self.block_size.get().lower() == "auto"))
        self.cancel_event = threading.Event()
        self.executor = None # Para gerenciar o ThreadPoolExecutor

        self._create_widgets()

    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10 10 10 10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Configuração de grid para responsividade
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(7, weight=1)

        # Pasta de Imagens
        ttk.Label(main_frame, text="Pasta de Imagens:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(main_frame, textvariable=self.input_folder, width=50).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="Procurar", command=self.browse_folder).grid(row=0, column=2, sticky=tk.E)

        # astcenc Path
        ttk.Label(main_frame, text="astcenc Path:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(main_frame, textvariable=self.astcenc_path, width=50).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="Procurar", command=self.browse_astcenc).grid(row=1, column=2, sticky=tk.E)

        # Tamanho do Bloco
        ttk.Label(main_frame, text="Tamanho do Bloco:").grid(row=2, column=0, sticky=tk.W, pady=2)
        block_combo = ttk.Combobox(main_frame, textvariable=self.block_size, width=15, values=["Auto"] + BLOCK_SIZES, state="readonly")
        block_combo.grid(row=2, column=1, sticky=tk.W, padx=5)
        block_combo.bind("<<ComboboxSelected>>", lambda e: self.auto.set(self.block_size.get().lower() == "auto"))

        # Qualidade
        ttk.Label(main_frame, text="Qualidade:").grid(row=3, column=0, sticky=tk.W, pady=2)
        quality_combo = ttk.Combobox(main_frame, textvariable=self.quality, width=15, values=["-fast", "-medium", "-thorough", "-exhaustive"], state="readonly")
        quality_combo.grid(row=3, column=1, sticky=tk.W, padx=5)

        # Botão de Tema (Dark/Light)
        if ttk_style_available:
            self.theme_button = ttk.Button(main_frame, text="Alternar Tema", command=self.toggle_theme)
            self.theme_button.grid(row=3, column=2, sticky=tk.E, padx=5)

        # Botões de Ação
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=10)
        self.btn_convert = ttk.Button(button_frame, text="Converter", command=self.start_conversion)
        self.btn_convert.pack(side=tk.LEFT, padx=5)
        self.btn_cancel = ttk.Button(button_frame, text="Cancelar", command=self.cancel_conversion, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=5)

        # Barra de Progresso
        self.progress = ttk.Progressbar(main_frame, orient="horizontal", mode="determinate")
        self.progress.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        # Log
        ttk.Label(main_frame, text="Log:").grid(row=6, column=0, sticky=tk.W)
        self.log = tk.Text(main_frame, height=10, state=tk.DISABLED, wrap=tk.WORD)
        self.log.grid(row=7, column=0, columnspan=3, sticky=(tk.N, tk.S, tk.E, tk.W))
        log_scrollbar = ttk.Scrollbar(main_frame, command=self.log.yview)
        log_scrollbar.grid(row=7, column=3, sticky=(tk.N, tk.S))
        self.log["yscrollcommand"] = log_scrollbar.set

        # Status Bar
        self.status_label = ttk.Label(main_frame, text="Pronto.", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.grid(row=8, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

    def load_config(self):
        try:
            with open(CONFIG_FILE, "r") as f:
                self.cfg = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.cfg = {}

    def save_config(self):
        cfg = {
            "input_folder": self.input_folder.get(),
            "astcenc_path": self.astcenc_path.get(),
            "block_size": self.block_size.get(),
            "quality": self.quality.get(),
            "theme": self.style.theme.name if self.style else ""
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(cfg, f, indent=4)
        except IOError as e:
            self.log_message(f"Erro ao salvar configuração: {e}", level="error")

    def toggle_theme(self):
        if not ttk_style_available: return
        current_theme = self.style.theme.name
        if current_theme == "darkly":
            self.style.theme_use("flatly") # Exemplo de tema claro
        else:
            self.style.theme_use("darkly") # Exemplo de tema escuro
        self.root.tk_setPalette(background=self.style.colors.bg)
        self.save_config()

    def browse_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.input_folder.set(d)

    def browse_astcenc(self):
        f = filedialog.askopenfilename(filetypes=[("Executável", "*.exe"), ("Todos os Arquivos", "*.*")])
        if f:
            self.astcenc_path.set(f)

    def log_message(self, msg, level="info"):
        self.root.after(0, lambda:
            self._insert_log_message(msg, level))

    def _insert_log_message(self, msg, level):
        self.log.config(state=tk.NORMAL)
        if level == "error":
            self.log.insert(tk.END, "ERRO: " + msg + "\n", "error")
        elif level == "warning":
            self.log.insert(tk.END, "AVISO: " + msg + "\n", "warning")
        else:
            self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

        # Configurar tags para cores
        self.log.tag_config("error", foreground="red")
        self.log.tag_config("warning", foreground="orange")

    def update_status(self, msg):
        self.root.after(0, lambda: self.status_label.config(text=msg))

    def choose_best_block(self, w, h, file_size):
        best, best_diff = None, float("inf")
        for b in BLOCK_SIZES:
            bx, by = map(int, b.split("x"))
            # Calcular o número de blocos necessários para cobrir a imagem
            blocks_x = math.ceil(w / bx)
            blocks_y = math.ceil(h / by)
            total_blocks = blocks_x * blocks_y
            # Cada bloco ASTC de 16 bytes
            est_size = total_blocks * 16
            diff = abs(est_size - file_size)
            if diff < best_diff:
                best_diff, best = diff, (bx, by)
        return best

    def pad_image(self, img, bx, by):
        w, h = img.size
        nw, nh = math.ceil(w / bx) * bx, math.ceil(h / by) * by
        if (nw, nh) == (w, h):
            return img
        new = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
        new.paste(img, (0, 0))
        return new

    def convert_one(self, path):
        if self.cancel_event.is_set():
            return f"Cancelado: {path}"
        try:
            norm_ignore_path = IGNORE_PATH.replace("\\", "/").lower()
            norm_path = path.replace("\\", "/").lower()
            if norm_ignore_path in norm_path:
                return f"Ignorado (padrão): {path}"

            astcenc = self.astcenc_path.get()
            out = os.path.splitext(path)[0] + ".astc"
            if os.path.exists(out):
                return f"Pulando: {path}"

            # Verificar se o arquivo de entrada existe e não está vazio
            if not os.path.exists(path) or os.path.getsize(path) == 0:
                raise FileNotFoundError(f"Arquivo de imagem inválido ou vazio: {path}")

            file_size = os.path.getsize(path)
            with Image.open(path) as img:
                w, h = img.size
                if self.auto.get():
                    bx, by = self.choose_best_block(w, h, file_size)
                else:
                    bx, by = map(int, self.block_size.get().split("x"))
                
                # Converter para RGBA antes de salvar, se necessário
                if img.mode != "RGBA":
                    img = img.convert("RGBA")

                img = self.pad_image(img, bx, by)
                
                # Usar um nome de arquivo temporário mais robusto
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="astc_")
                os.close(tmp_fd) # Fechar o descritor de arquivo imediatamente
                img.save(tmp_path, "PNG", compress_level=1)

            if self.cancel_event.is_set():
                try: os.remove(tmp_path)
                except OSError: pass
                return f"Cancelado: {path}"

            cmd = [astcenc, "-cl", tmp_path, out, f"{bx}x{by}", self.quality.get()]
            
            # Adicionar timeout para subprocess.run
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300) # 5 minutos de timeout
            
            try: os.remove(tmp_path)
            except OSError: pass

            if res.returncode != 0:
                error_msg = res.stderr.strip() if res.stderr else "Erro desconhecido"
                return f"ERRO em {os.path.basename(path)}: {error_msg}"
            else:
                # Remover o arquivo original apenas se a conversão for bem-sucedida
                try:
                    os.remove(path)
                except OSError as e:
                    self.log_message(f"AVISO: Não foi possível remover o arquivo original {path}: {e}", level="warning")
                return f"Convertido ({bx}x{by}): {path}"
        except FileNotFoundError as e:
            return f"ERRO: {e}"
        except subprocess.TimeoutExpired:
            try: os.remove(tmp_path)
            except OSError: pass
            return f"ERRO em {os.path.basename(path)}: O processo de conversão excedeu o tempo limite."
        except Exception as e:
            return f"ERRO: {e}"

    def start_conversion(self):
        inp = self.input_folder.get()
        astc = self.astcenc_path.get()
        if not os.path.isdir(inp):
            messagebox.showerror("Erro", "A pasta de imagens não existe ou é inválida.")
            return
        if not os.path.isfile(astc):
            messagebox.showerror("Erro", "O caminho do astcenc não existe ou é inválido.")
            return

        self.save_config()
        self.cancel_event.clear()
        self.btn_convert.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL)
        self.update_status("Iniciando conversão...")
        self.log.delete(1.0, tk.END)

        img_files = [
            os.path.join(r, f)
            for r, _, fs in os.walk(inp)
            for f in fs
            if f.lower().endswith((".png", ".jpg", ".jpeg",
                                    ".bmp", ".tga", ".tif", ".tiff", ".webp"))
        ]

        total_files = len(img_files)
        if total_files == 0:
            messagebox.showinfo("Nada encontrado", "Nenhuma imagem válida encontrada na pasta especificada.")
            self.finish_conversion()
            return

        self.progress["maximum"] = total_files
        self.progress["value"] = 0
        self.processed_count = 0

        self.executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 4) # Limitar workers para evitar sobrecarga
        futures = [self.executor.submit(self.convert_one, path) for path in img_files]

        # Iniciar um thread para monitorar os futuros
        threading.Thread(target=self._monitor_conversion, args=(futures,)).start()

    def _monitor_conversion(self, futures):
        for future in as_completed(futures):
            if self.cancel_event.is_set():
                break # Sair do loop se o cancelamento for solicitado
            result = future.result()
            self.log_message(result)
            self.processed_count += 1
            self.root.after(0, lambda: self.progress.set(self.processed_count))
        
        # Garantir que todos os threads são encerrados
        self.executor.shutdown(wait=True)
        self.root.after(0, self.finish_conversion)

    def cancel_conversion(self):
        self.cancel_event.set()
        self.btn_cancel.config(state=tk.DISABLED)
        self.update_status("Cancelamento solicitado...")
        # Não chamar finish_conversion aqui, será chamado pelo _monitor_conversion

    def finish_conversion(self):
        self.btn_convert.config(state=tk.NORMAL)
        self.btn_cancel.config(state=tk.DISABLED)
        if self.cancel_event.is_set():
            self.update_status("Conversão cancelada.")
            messagebox.showinfo("Cancelado", "Conversão foi cancelada pelo usuário.")
        else:
            self.update_status("Conversão concluída!")
            messagebox.showinfo("Pronto", "Conversão concluída!")
        self.cancel_event.clear() # Limpar o evento para a próxima conversão

if __name__ == "__main__":
    root = tk.Tk()
    app = ASTCConverterGUI(root)
    root.mainloop()


