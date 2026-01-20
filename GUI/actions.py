"""GitHub Actions dialog for FastGH."""

import wx
import webbrowser
import platform
import threading
from application import get_app
from models.repository import Repository
from models.workflow import Workflow, WorkflowRun, WorkflowJob
from . import theme


class ActionsDialog(wx.Dialog):
    """Dialog for viewing GitHub Actions workflow runs."""

    def __init__(self, parent, repo: Repository):
        self.repo = repo
        self.app = get_app()
        self.account = self.app.currentAccount
        self.owner = repo.owner
        self.repo_name = repo.name
        self.workflows = []
        self.runs = []

        title = f"Actions - {repo.full_name}"
        wx.Dialog.__init__(self, parent, title=title, size=(950, 650))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load workflows first, then runs
        self.load_workflows()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Filter row
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Workflow filter
        wf_label = wx.StaticText(self.panel, label="&Workflow:")
        filter_sizer.Add(wf_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.workflow_choice = wx.Choice(self.panel, choices=["All Workflows"])
        self.workflow_choice.SetSelection(0)
        filter_sizer.Add(self.workflow_choice, 1, wx.RIGHT, 15)

        # Status filter
        status_label = wx.StaticText(self.panel, label="&Status:")
        filter_sizer.Add(status_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.status_choice = wx.Choice(self.panel, choices=[
            "All",
            "Completed",
            "In Progress",
            "Queued"
        ])
        self.status_choice.SetSelection(0)
        filter_sizer.Add(self.status_choice, 0, wx.RIGHT, 15)

        self.refresh_btn = wx.Button(self.panel, label="&Refresh")
        filter_sizer.Add(self.refresh_btn, 0)

        main_sizer.Add(filter_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Workflow runs list
        list_label = wx.StaticText(self.panel, label="Workflow &Runs:")
        main_sizer.Add(list_label, 0, wx.LEFT, 10)

        self.runs_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.runs_list, 1, wx.EXPAND | wx.ALL, 10)

        # Run details preview
        details_label = wx.StaticText(self.panel, label="Run &Details:")
        main_sizer.Add(details_label, 0, wx.LEFT, 10)

        self.details_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_DONTWRAP,
            size=(900, 100)
        )
        main_sizer.Add(self.details_text, 0, wx.EXPAND | wx.ALL, 10)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.view_btn = wx.Button(self.panel, label="&View Details")
        btn_sizer.Add(self.view_btn, 0, wx.RIGHT, 5)

        self.rerun_btn = wx.Button(self.panel, label="Re-r&un")
        btn_sizer.Add(self.rerun_btn, 0, wx.RIGHT, 5)

        self.rerun_failed_btn = wx.Button(self.panel, label="Rerun &Failed")
        btn_sizer.Add(self.rerun_failed_btn, 0, wx.RIGHT, 5)

        self.cancel_btn = wx.Button(self.panel, label="Ca&ncel")
        btn_sizer.Add(self.cancel_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.workflow_choice.Bind(wx.EVT_CHOICE, self.on_filter_change)
        self.status_choice.Bind(wx.EVT_CHOICE, self.on_filter_change)
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        self.view_btn.Bind(wx.EVT_BUTTON, self.on_view)
        self.rerun_btn.Bind(wx.EVT_BUTTON, self.on_rerun)
        self.rerun_failed_btn.Bind(wx.EVT_BUTTON, self.on_rerun_failed)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        self.runs_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view)
        self.runs_list.Bind(wx.EVT_LISTBOX, self.on_selection_change)
        self.runs_list.Bind(wx.EVT_KEY_DOWN, self.on_key)

    def on_char_hook(self, event):
        """Handle key events."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def load_workflows(self):
        """Load workflows in background."""
        def do_load():
            workflows = self.account.get_workflows(self.owner, self.repo_name)
            wx.CallAfter(self.update_workflows, workflows)

        threading.Thread(target=do_load, daemon=True).start()

    def update_workflows(self, workflows):
        """Update workflows dropdown."""
        self.workflows = workflows
        self.workflow_choice.Clear()
        self.workflow_choice.Append("All Workflows")

        for wf in workflows:
            self.workflow_choice.Append(wf.name)

        self.workflow_choice.SetSelection(0)

        # Load runs
        self.load_runs()

    def load_runs(self):
        """Load workflow runs in background."""
        self.runs_list.Clear()
        self.runs_list.Append("Loading...")
        self.runs = []
        self.details_text.SetValue("")

        # Get filter values
        wf_idx = self.workflow_choice.GetSelection()
        workflow_id = None
        if wf_idx > 0 and wf_idx <= len(self.workflows):
            workflow_id = self.workflows[wf_idx - 1].id

        status_idx = self.status_choice.GetSelection()
        status = None
        if status_idx == 1:
            status = "completed"
        elif status_idx == 2:
            status = "in_progress"
        elif status_idx == 3:
            status = "queued"

        def do_load():
            runs = self.account.get_workflow_runs(
                self.owner, self.repo_name,
                workflow_id=workflow_id,
                status=status
            )
            wx.CallAfter(self.update_runs_list, runs)

        threading.Thread(target=do_load, daemon=True).start()

    def update_runs_list(self, runs):
        """Update the runs list."""
        self.runs = runs
        self.runs_list.Clear()

        if not runs:
            self.runs_list.Append("No workflow runs found")
        else:
            for run in runs:
                self.runs_list.Append(run.format_display())

        self.update_buttons()

    def update_buttons(self):
        """Update button states based on selection."""
        run = self.get_selected_run()
        has_selection = run is not None

        self.view_btn.Enable(has_selection)
        self.open_browser_btn.Enable(has_selection)

        # Rerun is available for completed runs
        can_rerun = has_selection and run.status == "completed"
        self.rerun_btn.Enable(can_rerun)

        # Rerun failed is only for failed runs
        can_rerun_failed = has_selection and run.status == "completed" and run.conclusion == "failure"
        self.rerun_failed_btn.Enable(can_rerun_failed)

        # Cancel is only for in-progress or queued runs
        can_cancel = has_selection and run.status in ("in_progress", "queued")
        self.cancel_btn.Enable(can_cancel)

    def get_selected_run(self) -> WorkflowRun | None:
        """Get the currently selected run."""
        selection = self.runs_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.runs):
            return self.runs[selection]
        return None

    def on_filter_change(self, event):
        """Handle filter change."""
        self.load_runs()

    def on_refresh(self, event):
        """Refresh the runs list."""
        self.load_runs()

    def on_view(self, event):
        """View run details in a dialog."""
        run = self.get_selected_run()
        if run:
            dlg = ViewWorkflowRunDialog(self, self.repo, run)
            dlg.ShowModal()
            dlg.Destroy()
            # Refresh in case status changed
            self.load_runs()

    def on_rerun(self, event):
        """Re-run the workflow."""
        run = self.get_selected_run()
        if not run:
            return

        result = wx.MessageBox(
            f"Re-run workflow '{run.name}' #{run.run_number}?",
            "Confirm Re-run",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result == wx.YES:
            def do_rerun():
                success = self.account.rerun_workflow(self.owner, self.repo_name, run.id)
                wx.CallAfter(self.handle_rerun_result, success)

            threading.Thread(target=do_rerun, daemon=True).start()

    def handle_rerun_result(self, success):
        """Handle rerun result."""
        if success:
            wx.MessageBox("Workflow re-run started!", "Success", wx.OK | wx.ICON_INFORMATION)
            self.load_runs()
        else:
            wx.MessageBox("Failed to re-run workflow.", "Error", wx.OK | wx.ICON_ERROR)

    def on_rerun_failed(self, event):
        """Re-run only failed jobs."""
        run = self.get_selected_run()
        if not run:
            return

        result = wx.MessageBox(
            f"Re-run failed jobs for '{run.name}' #{run.run_number}?",
            "Confirm Re-run Failed Jobs",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result == wx.YES:
            def do_rerun():
                success = self.account.rerun_failed_jobs(self.owner, self.repo_name, run.id)
                wx.CallAfter(self.handle_rerun_result, success)

            threading.Thread(target=do_rerun, daemon=True).start()

    def on_cancel(self, event):
        """Cancel the workflow run."""
        run = self.get_selected_run()
        if not run:
            return

        result = wx.MessageBox(
            f"Cancel workflow run '{run.name}' #{run.run_number}?",
            "Confirm Cancel",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result == wx.YES:
            def do_cancel():
                success = self.account.cancel_workflow_run(self.owner, self.repo_name, run.id)
                wx.CallAfter(self.handle_cancel_result, success)

            threading.Thread(target=do_cancel, daemon=True).start()

    def handle_cancel_result(self, success):
        """Handle cancel result."""
        if success:
            wx.MessageBox("Workflow run cancelled!", "Success", wx.OK | wx.ICON_INFORMATION)
            self.load_runs()
        else:
            wx.MessageBox("Failed to cancel workflow run.", "Error", wx.OK | wx.ICON_ERROR)

    def on_open_browser(self, event):
        """Open run in browser."""
        run = self.get_selected_run()
        if run:
            webbrowser.open(run.html_url)

    def on_selection_change(self, event):
        """Handle selection change - show run details."""
        self.update_buttons()
        run = self.get_selected_run()
        if run:
            self.show_run_preview(run)

    def show_run_preview(self, run: WorkflowRun):
        """Show run preview in details text."""
        lines = []
        lines.append(f"Workflow: {run.name}")
        lines.append(f"Run: #{run.run_number} (attempt {run.run_attempt})")
        lines.append(f"Status: {run.get_status_text()}")
        lines.append(f"Event: {run.event}")
        lines.append(f"Branch: {run.head_branch} ({run.head_sha})")
        lines.append(f"Actor: {run.actor_login}")
        if run.created_at:
            lines.append(f"Started: {run.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

        sep = "\r\n" if platform.system() != "Darwin" else "\n"
        self.details_text.SetValue(sep.join(lines))

    def on_key(self, event):
        """Handle key events."""
        key = event.GetKeyCode()
        if key == wx.WXK_RETURN:
            self.on_view(None)
        else:
            event.Skip()

    def on_close(self, event):
        """Close the dialog."""
        self.EndModal(wx.ID_CLOSE)


class ViewWorkflowRunDialog(wx.Dialog):
    """Dialog for viewing full workflow run details with jobs."""

    def __init__(self, parent, repo: Repository, run: WorkflowRun):
        self.repo = repo
        self.run = run
        self.app = get_app()
        self.account = self.app.currentAccount
        self.jobs = []

        title = f"Workflow Run #{run.run_number}"
        wx.Dialog.__init__(self, parent, title=title, size=(900, 700))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load jobs
        self.load_jobs()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Run info
        info_label = wx.StaticText(self.panel, label="Run &Information:")
        main_sizer.Add(info_label, 0, wx.LEFT | wx.TOP, 10)

        self.info_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_DONTWRAP,
            size=(850, 120)
        )
        main_sizer.Add(self.info_text, 0, wx.EXPAND | wx.ALL, 10)

        # Build info
        self.update_info_text()

        # Jobs list
        jobs_label = wx.StaticText(self.panel, label="&Jobs:")
        main_sizer.Add(jobs_label, 0, wx.LEFT, 10)

        self.jobs_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.jobs_list, 1, wx.EXPAND | wx.ALL, 10)

        # Steps list (for selected job)
        steps_label = wx.StaticText(self.panel, label="&Steps:")
        main_sizer.Add(steps_label, 0, wx.LEFT, 10)

        self.steps_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.steps_list, 1, wx.EXPAND | wx.ALL, 10)

        # Buttons row 1
        btn_sizer1 = wx.BoxSizer(wx.HORIZONTAL)

        self.view_logs_btn = wx.Button(self.panel, label="View &Logs")
        btn_sizer1.Add(self.view_logs_btn, 0, wx.RIGHT, 5)

        self.rerun_btn = wx.Button(self.panel, label="Re-r&un All")
        btn_sizer1.Add(self.rerun_btn, 0, wx.RIGHT, 5)

        self.rerun_failed_btn = wx.Button(self.panel, label="Rerun &Failed")
        btn_sizer1.Add(self.rerun_failed_btn, 0, wx.RIGHT, 5)

        self.cancel_btn = wx.Button(self.panel, label="Ca&ncel")
        btn_sizer1.Add(self.cancel_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer1.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.open_job_btn = wx.Button(self.panel, label="Open &Job in Browser")
        btn_sizer1.Add(self.open_job_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer1.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer1, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)
        self.update_buttons()

    def update_info_text(self):
        """Update the info text."""
        r = self.run
        lines = []
        lines.append(f"Workflow: {r.name}")
        lines.append(f"Run Number: #{r.run_number} (attempt {r.run_attempt})")
        lines.append(f"Status: {r.get_status_text()}")
        lines.append(f"Event: {r.event}")
        lines.append(f"Branch: {r.head_branch}")
        lines.append(f"Commit: {r.head_sha}")
        lines.append(f"Actor: {r.actor_login}")
        if r.triggering_actor_login and r.triggering_actor_login != r.actor_login:
            lines.append(f"Triggered by: {r.triggering_actor_login}")
        if r.created_at:
            lines.append(f"Created: {r.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if r.run_started_at:
            lines.append(f"Started: {r.run_started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if r.updated_at:
            lines.append(f"Updated: {r.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")

        sep = "\r\n" if platform.system() != "Darwin" else "\n"
        self.info_text.SetValue(sep.join(lines))

    def load_jobs(self):
        """Load jobs in background."""
        self.jobs_list.Clear()
        self.jobs_list.Append("Loading jobs...")
        self.steps_list.Clear()

        def do_load():
            jobs = self.account.get_workflow_run_jobs(
                self.repo.owner, self.repo.name, self.run.id
            )
            wx.CallAfter(self.update_jobs_list, jobs)

        threading.Thread(target=do_load, daemon=True).start()

    def update_jobs_list(self, jobs):
        """Update the jobs list."""
        self.jobs = jobs
        self.jobs_list.Clear()

        if not jobs:
            self.jobs_list.Append("No jobs found")
        else:
            for job in jobs:
                self.jobs_list.Append(job.format_display())

        self.update_buttons()

    def update_buttons(self):
        """Update button states."""
        r = self.run

        # Rerun is available for completed runs
        can_rerun = r.status == "completed"
        self.rerun_btn.Enable(can_rerun)

        # Rerun failed is only for failed runs
        can_rerun_failed = r.status == "completed" and r.conclusion == "failure"
        self.rerun_failed_btn.Enable(can_rerun_failed)

        # Cancel is only for in-progress or queued runs
        can_cancel = r.status in ("in_progress", "queued")
        self.cancel_btn.Enable(can_cancel)

        # Job-specific buttons
        job = self.get_selected_job()
        self.open_job_btn.Enable(job is not None)
        self.view_logs_btn.Enable(job is not None)

    def get_selected_job(self) -> WorkflowJob | None:
        """Get the currently selected job."""
        selection = self.jobs_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.jobs):
            return self.jobs[selection]
        return None

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.view_logs_btn.Bind(wx.EVT_BUTTON, self.on_view_logs)
        self.rerun_btn.Bind(wx.EVT_BUTTON, self.on_rerun)
        self.rerun_failed_btn.Bind(wx.EVT_BUTTON, self.on_rerun_failed)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.open_job_btn.Bind(wx.EVT_BUTTON, self.on_open_job)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        self.jobs_list.Bind(wx.EVT_LISTBOX, self.on_job_selection_change)
        self.jobs_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view_logs)

    def on_char_hook(self, event):
        """Handle key events."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def on_job_selection_change(self, event):
        """Handle job selection change - show steps."""
        self.update_buttons()
        job = self.get_selected_job()
        if job:
            self.show_job_steps(job)

    def show_job_steps(self, job: WorkflowJob):
        """Show steps for the selected job."""
        self.steps_list.Clear()

        if not job.steps:
            self.steps_list.Append("No steps")
            return

        for step in job.steps:
            status = step.get('status', '')
            conclusion = step.get('conclusion', '')
            name = step.get('name', 'Unknown step')

            if status == 'completed':
                if conclusion == 'success':
                    icon = "✓"
                elif conclusion == 'failure':
                    icon = "✗"
                elif conclusion == 'skipped':
                    icon = "⊘"
                else:
                    icon = "?"
            elif status == 'in_progress':
                icon = "●"
            elif status == 'queued':
                icon = "○"
            else:
                icon = "?"

            self.steps_list.Append(f"{icon} {name}")

    def on_rerun(self, event):
        """Re-run the workflow."""
        result = wx.MessageBox(
            f"Re-run workflow '{self.run.name}' #{self.run.run_number}?",
            "Confirm Re-run",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result == wx.YES:
            def do_rerun():
                success = self.account.rerun_workflow(
                    self.repo.owner, self.repo.name, self.run.id
                )
                wx.CallAfter(self.handle_rerun_result, success)

            threading.Thread(target=do_rerun, daemon=True).start()

    def handle_rerun_result(self, success):
        """Handle rerun result."""
        if success:
            wx.MessageBox("Workflow re-run started!", "Success", wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox("Failed to re-run workflow.", "Error", wx.OK | wx.ICON_ERROR)

    def on_rerun_failed(self, event):
        """Re-run only failed jobs."""
        result = wx.MessageBox(
            f"Re-run failed jobs for '{self.run.name}' #{self.run.run_number}?",
            "Confirm Re-run Failed Jobs",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result == wx.YES:
            def do_rerun():
                success = self.account.rerun_failed_jobs(
                    self.repo.owner, self.repo.name, self.run.id
                )
                wx.CallAfter(self.handle_rerun_result, success)

            threading.Thread(target=do_rerun, daemon=True).start()

    def on_cancel(self, event):
        """Cancel the workflow run."""
        result = wx.MessageBox(
            f"Cancel workflow run '{self.run.name}' #{self.run.run_number}?",
            "Confirm Cancel",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result == wx.YES:
            def do_cancel():
                success = self.account.cancel_workflow_run(
                    self.repo.owner, self.repo.name, self.run.id
                )
                wx.CallAfter(self.handle_cancel_result, success)

            threading.Thread(target=do_cancel, daemon=True).start()

    def handle_cancel_result(self, success):
        """Handle cancel result."""
        if success:
            wx.MessageBox("Workflow run cancelled!", "Success", wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox("Failed to cancel workflow run.", "Error", wx.OK | wx.ICON_ERROR)

    def on_open_browser(self, event):
        """Open run in browser."""
        webbrowser.open(self.run.html_url)

    def on_open_job(self, event):
        """Open selected job in browser."""
        job = self.get_selected_job()
        if job:
            webbrowser.open(job.html_url)

    def on_view_logs(self, event):
        """View logs for the selected job."""
        job = self.get_selected_job()
        if job:
            dlg = JobLogsDialog(self, self.repo, job)
            dlg.ShowModal()
            dlg.Destroy()

    def on_close(self, event):
        """Close dialog."""
        self.EndModal(wx.ID_CLOSE)


class JobLogsDialog(wx.Dialog):
    """Dialog for viewing job logs."""

    def __init__(self, parent, repo: Repository, job: WorkflowJob):
        self.repo = repo
        self.job = job
        self.app = get_app()
        self.account = self.app.currentAccount

        title = f"Logs - {job.name}"
        wx.Dialog.__init__(self, parent, title=title, size=(1000, 700))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load logs
        self.load_logs()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Job info
        status_text = self.job.conclusion or self.job.status.replace("_", " ")
        info_label = wx.StaticText(self.panel, label=f"Job: {self.job.name} ({status_text})")
        main_sizer.Add(info_label, 0, wx.ALL, 10)

        # Logs text
        logs_label = wx.StaticText(self.panel, label="&Logs:")
        main_sizer.Add(logs_label, 0, wx.LEFT, 10)

        self.logs_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.HSCROLL,
            size=(950, 550)
        )
        # Use monospace font for logs
        font = wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.logs_text.SetFont(font)
        self.logs_text.SetValue("Loading logs...")
        main_sizer.Add(self.logs_text, 1, wx.EXPAND | wx.ALL, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.refresh_btn = wx.Button(self.panel, label="&Refresh")
        btn_sizer.Add(self.refresh_btn, 0, wx.RIGHT, 5)

        self.copy_btn = wx.Button(self.panel, label="&Copy All")
        btn_sizer.Add(self.copy_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        self.copy_btn.Bind(wx.EVT_BUTTON, self.on_copy)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def on_char_hook(self, event):
        """Handle key events."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def load_logs(self):
        """Load job logs in background."""
        self.logs_text.SetValue("Loading logs...")

        def do_load():
            logs = self.account.get_job_logs(self.repo.owner, self.repo.name, self.job.id)
            wx.CallAfter(self.update_logs, logs)

        threading.Thread(target=do_load, daemon=True).start()

    def update_logs(self, logs: str | None):
        """Update the logs text."""
        try:
            if logs:
                # Clean up ANSI escape codes for better readability
                import re
                logs = re.sub(r'\x1b\[[0-9;]*m', '', logs)
                self.logs_text.SetValue(logs)
            else:
                self.logs_text.SetValue("No logs available.\n\nLogs may not be available if:\n- The job hasn't started yet\n- The job is still in progress\n- The logs have expired")
        except RuntimeError:
            pass  # Dialog was destroyed

    def on_refresh(self, event):
        """Refresh logs."""
        self.load_logs()

    def on_copy(self, event):
        """Copy all logs to clipboard."""
        logs = self.logs_text.GetValue()
        if logs and wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(logs))
            wx.TheClipboard.Close()
            wx.MessageBox("Logs copied to clipboard.", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_open_browser(self, event):
        """Open job in browser."""
        webbrowser.open(self.job.html_url)

    def on_close(self, event):
        """Close dialog."""
        self.EndModal(wx.ID_CLOSE)
