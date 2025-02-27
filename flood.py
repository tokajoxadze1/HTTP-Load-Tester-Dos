import ttkbootstrap as ttk
import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import requests
import random
import string
from time import perf_counter
from urllib.parse import urlparse
from queue import Queue
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# გამოყენებული იქნება შემთხვევითი მონაცემების და User-Agent-ების გენერაციისთვის
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64)',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)'
]

def random_string(length=20):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

class LoadTesterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("HTTP Load Tester")
        self.running = False
        self.queue = Queue()
        self.update_interval = 500  # ms
        
        self.setup_gui()
        self.setup_chart()

    def setup_gui(self):
        # გამოყენება PanedWindow-ის, რათა განლაგდეს მარცხენა და მარჯვენა ფანჯრები
        self.pw = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.pw.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # მარცხენა ფრეიმი - პარამეტრები და ლოგი
        self.left_frame = ttk.Frame(self.pw)
        self.pw.add(self.left_frame, weight=1)
        
        # მარჯვენა ფრეიმი - სტატისტიკა და გრაფიკი
        self.right_frame = ttk.Frame(self.pw)
        self.pw.add(self.right_frame, weight=2)
        
        # პარამეტრების ჩარჩო მარცხენა მხარეს
        parameters_frame = ttk.Labelframe(self.left_frame, text="ტესტის პარამეტრები", padding=10)
        parameters_frame.pack(fill=tk.X, pady=5)
        
        # URL შეყვანა
        ttk.Label(parameters_frame, text="URL:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.url_entry = ttk.Entry(parameters_frame, width=40)
        self.url_entry.grid(row=0, column=1, padx=5, pady=2)
        
        # პარამეტრები: ნაკადები, მოთხოვნები/ნაკადი, Timeout
        params = [
            ("ნაკადები", "threads", 1, 100, 10),
            ("მოთხოვნები/ნაკადი", "requests", 1, 1000, 50),
            ("Timeout (წმ)", "timeout", 1, 60, 5)
        ]
        row_index = 1
        for label, name, min_val, max_val, default in params:
            ttk.Label(parameters_frame, text=f"{label}:").grid(row=row_index, column=0, sticky=tk.W, padx=5, pady=2)
            entry = ttk.Spinbox(parameters_frame, from_=min_val, to=max_val, width=10)
            entry.set(default)
            entry.grid(row=row_index, column=1, padx=5, pady=2, sticky=tk.W)
            setattr(self, f"{name}_entry", entry)
            row_index += 1

        # სტრატეგიის (MODE) არჩევა
        ttk.Label(parameters_frame, text="სტრატეგია:").grid(row=row_index, column=0, sticky=tk.W, padx=5, pady=2)
        self.strategy_var = tk.StringVar()
        self.strategy_combo = ttk.Combobox(parameters_frame, textvariable=self.strategy_var, state="readonly", width=25)
        self.strategy_combo['values'] = [
            "Standard GET", 
            "Randomized GET", 
            "POST Flood", 
            "Keep-Alive Flood",
            "HEAD Flood",
            "PUT Flood",
            "Combined Flood"
        ]
        self.strategy_combo.current(0)
        self.strategy_combo.grid(row=row_index, column=1, padx=5, pady=2, sticky=tk.W)
        
        # კონტროლის ღილაკები
        btn_frame = ttk.Frame(self.left_frame)
        btn_frame.pack(pady=10)
        self.start_btn = ttk.Button(btn_frame, text="ტესტის დაწყება", command=self.start_test, bootstyle="success")
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="შეჩერება", state=tk.DISABLED, command=self.stop_test, bootstyle="danger")
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # ლოგის ჩარჩო
        log_frame = ttk.Labelframe(self.left_frame, text="ლოგი", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=15, bg="#2e2e2e", fg="white", insertbackground="white")
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log_area.tag_config("success", foreground="lime")
        self.log_area.tag_config("error", foreground="red")
        
        # სტატისტიკის ჩარჩო მარჯვენა მხარეს
        stats_frame = ttk.Labelframe(self.right_frame, text="რეალური დროის სტატისტიკა", padding=10)
        stats_frame.pack(fill=tk.X, pady=5)
        
        stats_labels = [
            ("მოთხოვნები:", "total_requests"),
            ("წარმატებული:", "success"),
            ("ჩავარდნილი:", "failures"),
            ("RPS:", "rps"),
            ("დრო:", "time")
        ]
        self.stats_values = {}
        for i, (text, var_name) in enumerate(stats_labels):
            frame = ttk.Frame(stats_frame)
            frame.grid(row=0, column=i, padx=10, pady=5)
            ttk.Label(frame, text=text).pack()
            label = ttk.Label(frame, text="0", font=('Helvetica', 14))
            label.pack()
            self.stats_values[var_name] = label
        
        self.total_requests_label = self.stats_values["total_requests"]
        self.success_label = self.stats_values["success"]
        self.failures_label = self.stats_values["failures"]
        self.rps_label = self.stats_values["rps"]
        self.time_label = self.stats_values["time"]

    def setup_chart(self):
        # გრაფიკის ჩარჩო მარჯვენა მხარეს
        self.chart_frame = ttk.Frame(self.right_frame)
        self.chart_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # matplotlib გრაფიკის კონფიგურაცია მუქი რეჟიმისთვის
        self.fig, self.ax = plt.subplots(figsize=(6, 3), facecolor="#2e2e2e")
        self.ax.set_facecolor("#3e3e3e")
        self.ax.tick_params(colors="white")
        self.ax.title.set_color("white")
        self.ax.xaxis.label.set_color("white")
        self.ax.yaxis.label.set_color("white")
        self.ax.set_title("Requests Per Second")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("RPS")
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.timestamps = []
        self.rps_values = []

    def validate_url(self, url):
        try:
            result = urlparse(url)
            return all([result.scheme in ['http', 'https'], result.netloc])
        except Exception:
            return False

    def log_message(self, message, tag=None):
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, message + "\n", tag)
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)

    def update_stats(self):
        while not self.queue.empty():
            success = self.queue.get()
            if success is not None:
                if success:
                    self.success += 1
                else:
                    self.failures += 1
                self.total_requests += 1
                
                # განახლება სტატისტიკური ველების მნიშვნელობები
                self.total_requests_label.config(text=str(self.total_requests))
                self.success_label.config(text=f"{self.success} ({self.success/self.total_requests:.1%})")
                self.failures_label.config(text=f"{self.failures} ({self.failures/self.total_requests:.1%})")
                
                elapsed = perf_counter() - self.start_time
                current_rps = self.total_requests / elapsed
                self.timestamps.append(elapsed)
                self.rps_values.append(current_rps)
                
                self.ax.clear()
                self.ax.plot(self.timestamps, self.rps_values, 'lime')
                self.ax.set_title("Requests Per Second", color="white")
                self.ax.set_xlabel("Time (s)", color="white")
                self.ax.set_ylabel("RPS", color="white")
                self.ax.tick_params(colors="white")
                self.ax.set_facecolor("#3e3e3e")
                self.canvas.draw()

        if self.running:
            self.root.after(self.update_interval, self.update_stats)

    def worker(self):
        strategy = self.strategy_var.get()
        session = requests.Session()
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        # "Keep-Alive Flood" დროს, დაყენდება ჰედერში "keep-alive"
        if strategy == "Keep-Alive Flood":
            headers["Connection"] = "keep-alive"
        
        # დადგენილდება საერთო მოთხოვნების რაოდენობა
        limit = self.num_threads * self.requests_per_thread
        
        while self.running and self.requests_sent < limit:
            try:
                if strategy == "Standard GET":
                    response = session.get(self.url, timeout=self.timeout, headers=headers)
                elif strategy == "Randomized GET":
                    headers["User-Agent"] = random.choice(USER_AGENTS)
                    response = session.get(self.url, timeout=self.timeout, headers=headers)
                elif strategy == "POST Flood":
                    data = {"data": random_string(20)}
                    response = session.post(self.url, timeout=self.timeout, headers=headers, data=data)
                elif strategy == "Keep-Alive Flood":
                    response = session.get(self.url, timeout=self.timeout, headers=headers)
                elif strategy == "HEAD Flood":
                    response = session.head(self.url, timeout=self.timeout, headers=headers)
                elif strategy == "PUT Flood":
                    data = {"data": random_string(20)}
                    response = session.put(self.url, timeout=self.timeout, headers=headers, data=data)
                elif strategy == "Combined Flood":
                    method = random.choice(["GET", "POST", "HEAD", "PUT"])
                    if method == "GET":
                        response = session.get(self.url, timeout=self.timeout, headers=headers)
                    elif method == "POST":
                        data = {"data": random_string(20)}
                        response = session.post(self.url, timeout=self.timeout, headers=headers, data=data)
                    elif method == "HEAD":
                        response = session.head(self.url, timeout=self.timeout, headers=headers)
                    elif method == "PUT":
                        data = {"data": random_string(20)}
                        response = session.put(self.url, timeout=self.timeout, headers=headers, data=data)
                else:
                    response = session.get(self.url, timeout=self.timeout, headers=headers)
                    
                self.queue.put(response.ok)
                self.log_message(f"[{response.status_code}] {self.url} ({strategy})", "success")
            except Exception as e:
                self.queue.put(False)
                self.log_message(f"[ERROR] {str(e)} ({strategy})", "error")
            finally:
                self.requests_sent += 1

    def start_test(self):
        if self.running:
            return

        self.url = self.url_entry.get()
        if not self.validate_url(self.url):
            messagebox.showerror("არასწორი URL", "გთხოვთ შეიყვანეთ სწორი HTTP/HTTPS URL")
            return

        try:
            self.num_threads = int(self.threads_entry.get())
            self.requests_per_thread = int(self.requests_entry.get())
            self.timeout = int(self.timeout_entry.get())
        except ValueError:
            messagebox.showerror("შეცდომა", "მიუთითეთ სწორი რიცხვები!")
            return

        self.running = True
        self.start_time = perf_counter()
        self.total_requests = 0
        self.success = 0
        self.failures = 0
        self.requests_sent = 0
        
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.log_area.config(state=tk.NORMAL)
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state=tk.DISABLED)
        
        for _ in range(self.num_threads):
            thread = threading.Thread(target=self.worker)
            thread.daemon = True
            thread.start()
        
        self.root.after(self.update_interval, self.update_stats)

    def stop_test(self):
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        
        total_time = perf_counter() - self.start_time
        self.time_label.config(text=f"{total_time:.2f} წამ")
        self.rps_label.config(text=f"{self.total_requests/total_time:.2f}")

if __name__ == "__main__":
    root = ttk.Window(themename="darkly")
    root.geometry("1200x800")
    app = LoadTesterGUI(root)
    root.mainloop()
