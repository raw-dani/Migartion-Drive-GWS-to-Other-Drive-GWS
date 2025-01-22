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
        self.root.geometry("510x600")
        
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Email inputs
        ttk.Label(self.main_frame, text="Source Email:").grid(row=0, column=0, pady=5)
        self.source_email = ttk.Entry(self.main_frame, width=40)
        self.source_email.grid(row=0, column=1, columnspan=2, pady=5)
        
        ttk.Label(self.main_frame, text="Destination Email:").grid(row=1, column=0, pady=5)
        self.dest_email = ttk.Entry(self.main_frame, width=40)
        self.dest_email.grid(row=1, column=1, columnspan=2, pady=5)

        # Domain inputs
        ttk.Label(self.main_frame, text="Source Domain:").grid(row=2, column=0, pady=5)
        self.source_domain = ttk.Entry(self.main_frame, width=40)
        self.source_domain.grid(row=2, column=1, columnspan=2, pady=5)

        ttk.Label(self.main_frame, text="Target Domain:").grid(row=3, column=0, pady=5)
        self.target_domain = ttk.Entry(self.main_frame, width=40)
        self.target_domain.grid(row=3, column=1, columnspan=2, pady=5)
        
        # Migration options
        self.migration_options = ttk.LabelFrame(self.main_frame, text="Migration Options")
        self.migration_options.grid(row=4, column=0, columnspan=3, pady=5)
        
        self.my_drive_var = tk.BooleanVar(value=True)
        self.shared_drive_var = tk.BooleanVar(value=True)
        self.shared_with_me_var = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(self.migration_options, text="My Drive", variable=self.my_drive_var).grid(row=0, column=0, padx=5)
        ttk.Checkbutton(self.migration_options, text="Shared Drives", variable=self.shared_drive_var).grid(row=0, column=1, padx=5)
        ttk.Checkbutton(self.migration_options, text="Shared with me", variable=self.shared_with_me_var).grid(row=0, column=2, padx=5)
        
        # Progress bar
        self.progress = ttk.Progressbar(self.main_frame, length=300, mode='indeterminate')
        self.progress.grid(row=5, column=0, columnspan=3, pady=10)
        
        # Status text
        self.status_text = tk.Text(self.main_frame, height=15, width=60)
        self.status_text.grid(row=6, column=0, columnspan=3, pady=5)
        
        # Create button frame for better spacing
        self.button_frame = ttk.Frame(self.main_frame)
        self.button_frame.grid(row=7, column=0, columnspan=3, pady=10)

        # Style configuration with improved visibility
        style = ttk.Style()
        style.configure('Start.TButton', 
            background='#4CAF50',  # Bright green
            foreground='white',
            font=('Arial', 10, 'bold')
        )
        style.configure('Stop.TButton', 
            background='#F44336',  # Bright red
            foreground='white',
            font=('Arial', 10, 'bold')
        )
        style.map('Start.TButton',
            background=[('active', '#45a049')],  # Darker green on hover
            foreground=[('active', 'white')]
        )
        style.map('Stop.TButton',
            background=[('active', '#d32f2f')],  # Darker red on hover
            foreground=[('active', 'white')]
        )

        # Start button with enhanced visibility
        self.start_button = ttk.Button(
            self.button_frame, 
            text="Start Migration", 
            command=self.start_migration,
            style='Start.TButton',
            width=20
        )
        self.start_button.grid(row=0, column=0, padx=20)

        # Stop button with enhanced visibility
        self.stop_button = ttk.Button(
            self.button_frame, 
            text="Stop Migration", 
            command=self.stop_migration,
            style='Stop.TButton',
            width=20,
            state='disabled'
        )
        self.stop_button.grid(row=0, column=1, padx=20)

        # Add file transfer info frame
        self.transfer_info = ttk.LabelFrame(self.main_frame, text="Transfer Status")
        self.transfer_info.grid(row=5, column=0, columnspan=3, pady=5)

        # Current file label with wider width
        self.current_file_label = ttk.Label(self.transfer_info, text="Current File: None", width=60)
        self.current_file_label.grid(row=0, column=0, pady=2, padx=5)

        # Transfer type label with status indicators
        self.transfer_type_label = ttk.Label(self.transfer_info, text="Status: Idle", width=30)
        self.transfer_type_label.grid(row=1, column=0, pady=2, padx=5)

        # File count label with progress
        self.file_count_label = ttk.Label(self.transfer_info, text="Files: 0/0", width=20)
        self.file_count_label.grid(row=2, column=0, pady=2, padx=5)

        # Force update display
        self.root.update_idletasks()

    def update_transfer_info(self, file_name, transfer_type, current_count, total_count):
        """Update transfer information in UI"""
        status_text = transfer_type
        if transfer_type == "Downloading" and file_name.endswith('.shortcut'):
            status_text += " (Shortcut)"
        self.current_file_label.config(text=f"Current File: {file_name}")
        self.transfer_type_label.config(text=f"Status: {status_text}")
        self.file_count_label.config(text=f"Files: {current_count}/{total_count}")
        self.root.update()

    def update_status(self, message):
        self.status_text.insert(tk.END, f"{message}\n")
        self.status_text.see(tk.END)

    def start_migration(self):
        source = self.source_email.get()
        dest = self.dest_email.get()
        source_domain = self.source_domain.get()
        target_domain = self.target_domain.get()
        
        if not all([source, dest, source_domain, target_domain]):
            messagebox.showerror("Error", "Please fill in all required fields")
            return
        
        self.progress.start()
        self.start_button.state(['disabled'])
        thread = threading.Thread(target=self.run_migration, args=(source, dest, source_domain, target_domain))
        thread.start()

    def stop_migration(self):
        self.migration_running = False
        self.update_status("Migration stopped by user")
        self.progress.stop()
        self.start_button.state(['!disabled'])
        self.stop_button.state(['disabled'])

    def run_migration(self, source_email, dest_email, source_domain, target_domain):
        try:
            self.migration_running = True
            self.stop_button.state(['!disabled'])
            drive_manager = DriveManager()
            drive_manager.set_ui(self)
            self.update_status(f"Starting migration from {source_email} to {dest_email}")
            
            zip_path = None
            
            if self.my_drive_var.get():
                self.update_status("Migrating My Drive...")
                zip_path = drive_manager.download_drive(source_email)
                
            if self.shared_drive_var.get():
                self.update_status("Checking Shared Drives...")
                shared_drives = drive_manager.list_shared_drives(source_email)
                if not shared_drives:
                    self.update_status("No shared drives found, skipping...")
                else:
                    zip_path = drive_manager.download_shared_drive(source_email)                
                    
            if self.shared_with_me_var.get():
                self.update_status("Migrating Shared Files...")
                shared_files_zip_path = drive_manager.download_shared_with_me(source_email)
                if not zip_path:
                    zip_path = shared_files_zip_path            
            
            if zip_path:
                self.update_status("Extracting files...")
                extract_path = drive_manager.extract_drive(zip_path)
                
                self.update_status("Uploading to destination...")
                drive_manager.upload_drive(extract_path, dest_email, source_domain, target_domain)
                
                self.update_status("Migration completed successfully!")
            else:
                self.update_status("No files selected for migration")

            if not self.migration_running:
                return
                
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
