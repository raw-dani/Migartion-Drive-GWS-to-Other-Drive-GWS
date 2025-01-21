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
        
        # Email inputs
        ttk.Label(self.main_frame, text="Source Email:").grid(row=0, column=0, pady=5)
        self.source_email = ttk.Entry(self.main_frame, width=40)
        self.source_email.grid(row=0, column=1, columnspan=2, pady=5)
        
        ttk.Label(self.main_frame, text="Destination Email:").grid(row=1, column=0, pady=5)
        self.dest_email = ttk.Entry(self.main_frame, width=40)
        self.dest_email.grid(row=1, column=1, columnspan=2, pady=5)
        
        # Migration options
        self.migration_options = ttk.LabelFrame(self.main_frame, text="Migration Options")
        self.migration_options.grid(row=2, column=0, columnspan=3, pady=5)
        
        self.my_drive_var = tk.BooleanVar(value=True)
        self.shared_drive_var = tk.BooleanVar(value=True)
        self.shared_with_me_var = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(self.migration_options, text="My Drive", variable=self.my_drive_var).grid(row=0, column=0, padx=5)
        ttk.Checkbutton(self.migration_options, text="Shared Drives", variable=self.shared_drive_var).grid(row=0, column=1, padx=5)
        ttk.Checkbutton(self.migration_options, text="Shared with me", variable=self.shared_with_me_var).grid(row=0, column=2, padx=5)
        
        # Progress bar
        self.progress = ttk.Progressbar(self.main_frame, length=300, mode='indeterminate')
        self.progress.grid(row=3, column=0, columnspan=3, pady=10)
        
        # Status text
        self.status_text = tk.Text(self.main_frame, height=15, width=60)
        self.status_text.grid(row=4, column=0, columnspan=3, pady=5)
        
        # Start button
        self.start_button = ttk.Button(self.main_frame, text="Start Migration", command=self.start_migration)
        self.start_button.grid(row=5, column=0, columnspan=3, pady=10)

        # Add file transfer info frame
        self.transfer_info = ttk.LabelFrame(self.main_frame, text="Transfer Status")
        self.transfer_info.grid(row=3, column=0, columnspan=3, pady=5)
        
        # Current file label
        self.current_file_label = ttk.Label(self.transfer_info, text="Current File: None")
        self.current_file_label.grid(row=0, column=0, pady=2)
        
        # Transfer type label (Download/Upload)
        self.transfer_type_label = ttk.Label(self.transfer_info, text="Status: Idle")
        self.transfer_type_label.grid(row=1, column=0, pady=2)
        
        # File count label
        self.file_count_label = ttk.Label(self.transfer_info, text="Files: 0/0")
        self.file_count_label.grid(row=2, column=0, pady=2)

    def update_transfer_info(self, file_name, transfer_type, current_count, total_count):
        """Update transfer information in UI"""
        self.current_file_label.config(text=f"Current File: {file_name}")
        self.transfer_type_label.config(text=f"Status: {transfer_type}")
        self.file_count_label.config(text=f"Files: {current_count}/{total_count}")
        self.root.update()
    
    def update_status(self, message):
        self.status_text.insert(tk.END, f"{message}\n")
        self.status_text.see(tk.END)

    def start_migration(self):
        source = self.source_email.get()
        dest = self.dest_email.get()
        
        if not source or not dest:
            messagebox.showerror("Error", "Please enter both email addresses")
            return
        
        self.progress.start()
        self.start_button.state(['disabled'])
        thread = threading.Thread(target=self.run_migration, args=(source, dest))
        thread.start()

    def run_migration(self, source_email, dest_email):
        try:
            drive_manager = DriveManager()
            self.update_status(f"Starting migration from {source_email} to {dest_email}")
            
            if self.my_drive_var.get():
                self.update_status("Migrating My Drive...")
                zip_path = drive_manager.download_drive(source_email)
                
            if self.shared_drive_var.get():
                self.update_status("Migrating Shared Drives...")
                drive_manager.download_shared_drive(source_email)
                
            if self.shared_with_me_var.get():
                self.update_status("Migrating Shared Files...")
                drive_manager.download_shared_with_me(source_email)
            
            self.update_status("Extracting files...")
            extract_path = drive_manager.extract_drive(zip_path)
            
            self.update_status("Uploading to destination...")
            drive_manager.upload_drive(extract_path, dest_email)
            
            self.update_status("Migration completed successfully!")
            
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
