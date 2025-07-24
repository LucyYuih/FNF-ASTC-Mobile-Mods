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
MIN_SELECT_SIZE = (256, 256)
THUMB_SIZE = (96, 96)  # Reduced thumbnail size for better performance

class ASTCConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ASTC Converter with Selection")
        self.root.geometry("750x750")
        self.root.configure(bg='#2b2b2b')
        self.load_config()

        self.input_folder = tk.StringVar(value=self.cfg.get('input_folder', ''))
        self.astcenc_path = tk.StringVar(value=self.cfg.get('astcenc_path', ''))
        self.block_size = tk.StringVar(value=self.cfg.get('block_size', 'auto'))
        self.quality = tk.StringVar(value=self.cfg.get('quality', '-fast'))
        self.auto = tk.BooleanVar(value=(self.block_size.get().lower() == 'auto'))
        self.cancel_event = threading.Event()
        self.selected_images = []
        self.all_images = []
        self.filtered_images = []
        self.search_var = tk.StringVar()
        self.current_tab = tk.StringVar(value="all")
        
        # Performance optimization variables
        self.search_timer = None
        self.image_cache = {}

        self.build_main_ui()

    def build_main_ui(self):
        # Configure dark theme
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background='#2b2b2b')
        style.configure('TLabel', background='#2b2b2b', foreground='white')
        style.configure('TButton', background='#404040', foreground='white')
        style.configure('TEntry', background='#404040', foreground='white', fieldbackground='#404040')
        style.configure('TCombobox', background='#404040', foreground='white', fieldbackground='#404040')
        style.configure('TCheckbutton', background='#2b2b2b', foreground='white')
        style.configure('TNotebook', background='#2b2b2b')
        style.configure('TNotebook.Tab', background='#404040', foreground='white')
        
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Inputs
        ttk.Label(frame, text="Images Folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.input_folder, width=40).grid(row=0, column=1)
        ttk.Button(frame, text="Browse", command=self.browse_folder).grid(row=0, column=2)

        ttk.Label(frame, text="astcenc Path:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.astcenc_path, width=40).grid(row=1, column=1)
        ttk.Button(frame, text="Browse", command=self.browse_astcenc).grid(row=1, column=2)

        # Options
        ttk.Label(frame, text="Block Size:").grid(row=2, column=0, sticky="w", pady=5)
        block_combo = ttk.Combobox(frame, textvariable=self.block_size, width=10, values=['Auto'] + BLOCK_SIZES)
        block_combo.grid(row=2, column=1, sticky="w")
        block_combo.bind('<<ComboboxSelected>>', lambda e: self.auto.set(self.block_size.get().lower() == 'auto'))

        ttk.Label(frame, text="Quality:").grid(row=3, column=0, sticky="w", pady=5)
        quality_combo = ttk.Combobox(frame, textvariable=self.quality, width=10,
                                     values=['-fast', '-medium', '-thorough', '-exhaustive'])
        quality_combo.grid(row=3, column=1, sticky="w")

        # Buttons
        ttk.Button(frame, text="Select Images", command=self.open_selection_window).grid(row=4, column=0, pady=10)
        self.btn_convert = ttk.Button(frame, text="Convert", command=self.start_conversion)
        self.btn_convert.grid(row=4, column=1, pady=10)
        self.btn_cancel = ttk.Button(frame, text="Cancel", command=self.cancel_conversion, state=tk.DISABLED)
        self.btn_cancel.grid(row=4, column=2, pady=10)

        # Progress and log
        self.progress = ttk.Progressbar(frame, orient="horizontal", mode="determinate")
        self.progress.grid(row=5, column=0, columnspan=3, sticky="we", pady=5)
        ttk.Label(frame, text="Log:").grid(row=6, column=0, sticky="w")
        self.log = tk.Text(frame, height=10, bg='#404040', fg='white', insertbackground='white')
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
        f = filedialog.askopenfilename(filetypes=[('Executable', '*.exe'), ('All', '*.*')])
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

    def scan_all_images(self):
        """Scan all images without size limit"""
        all_imgs = []
        for r, _, files in os.walk(self.input_folder.get()):
            bn = os.path.basename(r).lower()
            if bn in (PIXEL_FOLDER_NAME, WEEK6_FOLDER_NAME): 
                continue
            for f in files:
                if f.lower().endswith(('.png','.jpg','.jpeg','.bmp','.tga','.tif','.tiff','.webp')):
                    p = os.path.join(r, f)
                    norm = p.replace('\\','/').lower()
                    if IGNORE_PATH.replace('\\','/').lower() in norm: 
                        continue
                    try:
                        with Image.open(p) as im: 
                            w, h = im.size
                        all_imgs.append({
                            'path': p,
                            'size': (w, h),
                            'selected': False,
                            'excluded': False
                        })
                    except: 
                        continue
        return all_imgs

    def scan_all(self):
        """Maintain compatibility with original code"""
        all_imgs = []
        for r, _, files in os.walk(self.input_folder.get()):
            bn = os.path.basename(r).lower()
            if bn in (PIXEL_FOLDER_NAME, WEEK6_FOLDER_NAME): 
                continue
            for f in files:
                if f.lower().endswith(('.png','.jpg','.jpeg','.bmp','.tga','.tif','.tiff','.webp')):
                    p = os.path.join(r, f)
                    norm = p.replace('\\','/').lower()
                    if IGNORE_PATH.replace('\\','/').lower() in norm: 
                        continue
                    all_imgs.append(p)
        return all_imgs

    def filter_images(self, search_term=""):
        """Filter images based on search term"""
        if not search_term:
            return self.all_images
        
        filtered = []
        search_lower = search_term.lower()
        for img in self.all_images:
            filename = os.path.basename(img['path']).lower()
            if search_lower in filename:
                filtered.append(img)
        return filtered

    def delayed_search(self):
        """Delayed search to improve performance"""
        if self.search_timer:
            self.root.after_cancel(self.search_timer)
        self.search_timer = self.root.after(300, self.perform_search)  # 300ms delay

    def perform_search(self):
        """Perform the actual search"""
        search_term = self.search_var.get()
        self.filtered_images = self.filter_images(search_term)
        self.current_batch = 0
        self.update_image_display()
        self.update_count_label()

    def on_search_change(self, *args):
        """Callback for search field change with debounce"""
        self.delayed_search()

    def calculate_columns(self, container_width):
        """Calculate optimal number of columns based on container width"""
        min_item_width = 120  # Minimum width for each image item
        max_cols = max(1, container_width // min_item_width*2)
        return min(max_cols, 12)  # Maximum 12 columns

    def get_images_for_tab(self):
        """Return images based on current tab"""
        if self.current_tab.get() == "all":
            return self.filtered_images
        elif self.current_tab.get() == "selected":
            return [img for img in self.filtered_images if img['selected']]
        elif self.current_tab.get() == "excluded":
            return [img for img in self.filtered_images if img['excluded']]
        return []

    def get_cached_image(self, path):
        """Get cached thumbnail or create new one"""
        if path in self.image_cache:
            return self.image_cache[path]
        
        try:
            im = Image.open(path)
            im.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(im)
            self.image_cache[path] = photo
            return photo
        except:
            return None

    def toggle_image_selection(self, img_info):
        """Toggle image selection"""
        img_info['selected'] = not img_info['selected']
        if img_info['selected']:
            img_info['excluded'] = False
        else:
            img_info['excluded'] = True
        
        # Only update the specific button instead of entire display
        self.update_count_label()

    def update_image_display(self):
        """Update image display with optimized performance"""
        # Clear current frame
        for widget in self.current_images_frame.winfo_children():
            widget.destroy()
        
        images_to_show = self.get_images_for_tab()
        
        if not images_to_show:
            no_images_label = tk.Label(self.current_images_frame, text="No images found", 
                                     bg='#2b2b2b', fg='white', font=('Arial', 12))
            no_images_label.pack(pady=20)
            return
        
        # Calculate dynamic columns based on window width
        try:
            container_width = self.current_images_frame.winfo_width()
            if container_width <= 1:  # Window not yet rendered
                container_width = 800  # Default width
        except:
            container_width = 800
        
        cols = self.calculate_columns(container_width)
        
        # Configure grid weights for responsive layout
        for i in range(cols):
            self.current_images_frame.columnconfigure(i, weight=1)
        
        # Display all images at once
        for idx, img_info in enumerate(images_to_show):
            row, col = divmod(idx, cols)
            p = img_info['path']
            w, h = img_info['size']
            
            # Frame for each image
            img_frame = tk.Frame(self.current_images_frame, bg='#404040', relief='raised', bd=1)
            img_frame.grid(row=row, column=col, padx=2, pady=2, sticky='nsew')
            
            # Get cached thumbnail
            photo = self.get_cached_image(p)
            if photo:
                lbl = tk.Label(img_frame, image=photo, bg='#404040')
                lbl.image = photo  # Keep reference
                lbl.pack(pady=1)
            
            # File name and size
            filename = os.path.basename(p)
            if len(filename) > 15:
                filename = filename[:12] + "..."
            info_text = f"{filename}\n({w}x{h})"
            info_lbl = tk.Label(img_frame, text=info_text, bg='#404040', fg='white', 
                              wraplength=100, justify='center', font=('Arial', 7))
            info_lbl.pack(pady=1)
            
            # Selection button
            btn_text = "Deselect" if img_info['selected'] else "Select"
            btn_color = '#ff6b6b' if img_info['selected'] else '#51cf66'
            
            btn = tk.Button(img_frame, text=btn_text, bg=btn_color, fg='white',
                          command=lambda img=img_info: self.toggle_image_selection(img),
                          font=('Arial', 7), relief='flat', pady=1)
            btn.pack(pady=1)

    def on_tab_change(self, event):
        """Callback for tab change"""
        try:
            selected_tab_index = event.widget.index(event.widget.select())
            tab_names = ["all", "selected", "excluded"]
            self.current_tab.set(tab_names[selected_tab_index])
            self.current_images_frame = self.tab_frames[selected_tab_index]
            self.current_batch = 0
            self.update_image_display()
        except:
            pass

    def open_selection_window(self):
        """Open selection window with search and tabs"""
        self.all_images = self.scan_all_images()
        if not self.all_images:
            messagebox.showinfo("Nothing", "No images found.")
            return
        
        # Initialize default selections
        for img in self.all_images:
            w, h = img['size']
            img['selected'] = not (w < MIN_SELECT_SIZE[0] and h < MIN_SELECT_SIZE[1])
            img['excluded'] = not img['selected']
        
        self.filtered_images = self.all_images
        
        sel = tk.Toplevel(self.root)
        sel.title("Image Selection")
        sel.geometry("1400x900")
        sel.configure(bg='#2b2b2b')
        
        # Search frame
        search_frame = tk.Frame(sel, bg='#2b2b2b')
        search_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Label(search_frame, text="Search:", bg='#2b2b2b', fg='white', 
                font=('Arial', 10, 'bold')).pack(side='left')
        search_entry = tk.Entry(search_frame, textvariable=self.search_var, bg='#404040', 
                               fg='white', insertbackground='white', font=('Arial', 10),
                               relief='flat', bd=5)
        search_entry.pack(side='left', fill='x', expand=True, padx=(10, 0))
        self.search_var.trace('w', self.on_search_change)
        
        # Notebook for tabs with improved style
        style = ttk.Style()
        style.configure('Custom.TNotebook', background='#2b2b2b', borderwidth=0)
        style.configure('Custom.TNotebook.Tab', background='#404040', foreground='white', 
                       padding=[20, 10], borderwidth=1)
        style.map('Custom.TNotebook.Tab', background=[('selected', '#51cf66')])
        
        notebook = ttk.Notebook(sel, style='Custom.TNotebook')
        notebook.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Create tab frames
        self.tab_frames = []
        tab_names = ['All', 'Selected', 'Excluded']
        
        for i, tab_name in enumerate(tab_names):
            # Main tab frame
            tab_frame = ttk.Frame(notebook)
            notebook.add(tab_frame, text=tab_name)
            
            # Canvas and scrollbar for images
            canvas = tk.Canvas(tab_frame, bg='#2b2b2b', highlightthickness=0)
            vsb = ttk.Scrollbar(tab_frame, orient='vertical', command=canvas.yview)
            hsb = ttk.Scrollbar(tab_frame, orient='horizontal', command=canvas.xview)
            
            images_frame = tk.Frame(canvas, bg='#2b2b2b')
            self.tab_frames.append(images_frame)
            
            images_frame.bind('<Configure>', lambda e, c=canvas: c.configure(scrollregion=c.bbox('all')))
            canvas.create_window((0, 0), window=images_frame, anchor='nw')
            canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            
            canvas.pack(side='left', fill='both', expand=True)
            vsb.pack(side='right', fill='y')
            hsb.pack(side='bottom', fill='x')
        
        # Set current frame as first
        self.current_images_frame = self.tab_frames[0]
        
        # Bind tab change
        notebook.bind('<<NotebookTabChanged>>', self.on_tab_change)
        
        # Bottom button frame
        btn_frame = tk.Frame(sel, bg='#2b2b2b')
        btn_frame.pack(fill='x', padx=10, pady=10)
        
        # Image counter
        self.count_label = tk.Label(btn_frame, text="", bg='#2b2b2b', fg='white', 
                                   font=('Arial', 10))
        self.count_label.pack(side='left')
        
        # Buttons with improved style
        btn_style = {'bg': '#51cf66', 'fg': 'white', 'font': ('Arial', 10, 'bold'), 
                    'relief': 'flat', 'padx': 15, 'pady': 5}
        
        ttk.Button(btn_frame, text="Confirm Selection", 
                  command=lambda: self.confirm_selection(sel)).pack(side='right', padx=5)
        
        btn_select_all = tk.Button(btn_frame, text="Select All", 
                                  command=self.select_all_images, **btn_style)
        btn_select_all.pack(side='right', padx=5)
        
        btn_style['bg'] = '#ff6b6b'
        btn_deselect_all = tk.Button(btn_frame, text="Deselect All", 
                                    command=self.deselect_all_images, **btn_style)
        btn_deselect_all.pack(side='right', padx=5)
        
        # Display initial images
        self.current_batch = 0
        self.update_image_display()
        self.update_count_label()

    def update_count_label(self):
        """Update image counter"""
        total = len(self.all_images)
        selected = len([img for img in self.all_images if img['selected']])
        filtered = len(self.filtered_images)
        self.count_label.config(text=f"Total: {total} | Filtered: {filtered} | Selected: {selected}")

    def select_all_images(self):
        """Select all filtered images"""
        for img in self.filtered_images:
            img['selected'] = True
            img['excluded'] = False
        self.current_batch = 0
        self.update_image_display()
        self.update_count_label()

    def deselect_all_images(self):
        """Deselect all filtered images"""
        for img in self.filtered_images:
            img['selected'] = False
            img['excluded'] = True
        self.current_batch = 0
        self.update_image_display()
        self.update_count_label()

    def confirm_selection(self, win):
        """Confirm selection and close window"""
        self.selected_images = [img['path'] for img in self.all_images if img['selected']]
        win.destroy()
        self.log_message(f"{len(self.selected_images)} images selected.")

    def start_conversion(self):
        all_imgs = self.scan_all()
        selected_paths = self.selected_images
        to_convert = selected_paths

        if not to_convert:
            messagebox.showwarning("Nothing", "No images to convert.")
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
            self.root.after(0, lambda: self.log_message(f"Cancelled: {path}"))
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
                self.root.after(0, lambda: self.log_message(f"Cancelled: {path}"))
                self.root.after(0, callback)
                return
            res = subprocess.run([self.astcenc_path.get(), '-cl', tmp, out, f'{bx}x{by}', self.quality.get()], capture_output=True, text=True)
            os.remove(tmp)
            if res.returncode != 0:
                self.root.after(0, lambda: self.log_message(f"ERROR in {os.path.basename(path)}: {res.stderr.strip()}"))
            else:
                os.remove(path)
                self.root.after(0, lambda: self.log_message(f"Converted: {path}"))
        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"Error: {e}"))
        finally:
            self.root.after(0, callback)

    def cancel_conversion(self):
        self.cancel_event.set()
        self.btn_cancel.config(state='disabled')
        self.log_message("Cancelling...")

    def finish_conversion(self):
        self.btn_convert.config(state='normal')
        self.btn_cancel.config(state='disabled')
        messagebox.showinfo("Done", "Conversion completed!" if not self.cancel_event.is_set() else "Cancelled by user.")

if __name__ == '__main__':
    root = tk.Tk()
    app = ASTCConverterGUI(root)
    root.mainloop()

