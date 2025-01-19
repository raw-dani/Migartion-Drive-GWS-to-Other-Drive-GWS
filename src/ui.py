import tkinter as tk
from tkinter import ttk, messagebox
from drive_manager import DriveManager
import logging
import threading
import os
from config import CONFIG

class MigrationUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Google Workspace Drive Migration Tool")
        self.root.geometry("800x600")
        
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        ttk.Label(self.main_frame, text="Source Email:").grid(row=0, column=0, pady=5)
        self.source_email = ttk.Entry(self.main_frame, width=40)
        self.source_email.grid(row=0, column=1, pady=5)
        
        ttk.Label(self.main_frame, text="Destination Email:").grid(row=1, column=0, pady=5)
        self.dest_email = ttk.Entry(self.main_frame, width=40)
        self.dest_email.grid(row=1, column=1, pady=5)
        
        self.progress = ttk.Progressbar(self.main_frame, length=300, mode='indeterminate')
        self.progress.grid(row=2, column=0, columnspan=2, pady=10)
        
        self.status_text = tk.Text(self.main_frame, height=15, width=60)
        self.status_text.grid(row=3, column=0, columnspan=2, pady=5)
        
        self.start_button = ttk.Button(self.main_frame, text="Start Migration", command=self.start_migration)
        self.start_button.grid(row=4, column=0, columnspan=2, pady=10)

    def update_status(self, message):
        self.status_text.insert(tk.END, f"{message}\n")
        self.status_text.see(tk.END)

    def start_migration(self):
        source = self.source_email.get()
        dest = self.dest_email.get()
        
        if not source or not dest:
            messagebox.showerror("Error", "Please enter both email addresses")
            return
        
        extract_path = os.path.join(CONFIG['TEMP_DIR'], 'extracted', source)
        if os.path.exists(extract_path):
            response = messagebox.askyesno(
                "Resume Migration",
                "Found existing files. Resume previous migration?",
                icon='question'
            )
            if response:
                self.update_status("Resuming from previous download...")
                self.run_upload_only(extract_path, dest)
                return
        
        self.progress.start()
        self.start_button.state(['disabled'])
        thread = threading.Thread(target=self.run_migration, args=(source, dest))
        thread.start()

    def run_migration(self, source_email, dest_email):
        try:
            drive_manager = DriveManager()
            self.update_status(f"Starting migration from {source_email} to {dest_email}")
            
            self.update_status("Downloading files...")
            zip_path = drive_manager.download_drive(source_email)
            
            self.update_status("Extracting files...")
            extract_path = drive_manager.extract_drive(zip_path)
            
            self.update_status("Uploading files...")
            drive_manager.upload_drive(extract_path, dest_email)
            
            self.update_status("Migration completed successfully!")
            
        except Exception as e:
            self.update_status(f"Error: {str(e)}")
        finally:
            self.progress.stop()
            self.start_button.state(['!disabled'])

    def run_upload_only(self, extract_path, dest_email):
        try:
            drive_manager = DriveManager()
            self.update_status("Resuming upload...")
            drive_manager.upload_drive(extract_path, dest_email)
            self.update_status("Upload completed successfully!")
        except Exception as e:
            self.update_status(f"Error: {str(e)}")
        finally:
            self.progress.stop()
            self.start_button.state(['!disabled'])

def main():
    root = tk.Tk()
    app = MigrationUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
