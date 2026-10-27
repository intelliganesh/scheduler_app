from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database.session import SessionLocal
from app.models.workflow import ReportJob
from app.services.workflow_service import WorkflowService


class SchedulerService:
    def __init__(self): self.scheduler = BackgroundScheduler(timezone=ZoneInfo("Asia/Kolkata"))
    def start(self): self.scheduler.start()
    def stop(self): self.scheduler.shutdown(wait=False)
    def sync_all(self):
        db = SessionLocal()
        try:
            for job in db.query(ReportJob).all(): self.sync_job(job)
        finally: db.close()
    def sync_job(self, job):
        job_id = f"report-job-{job.id}"
        if not job.enabled:
            self.scheduler.remove_job(job_id) if self.scheduler.get_job(job_id) else None; return
        if job.recurrence == "once":
            self.scheduler.add_job(self._run, DateTrigger(run_date=job.schedule_at, timezone=ZoneInfo("Asia/Kolkata")), args=[job.id], id=job_id, replace_existing=True, max_instances=1, misfire_grace_time=300)
            job.next_run_at = job.schedule_at
            return
        if job.recurrence.startswith("hourly_"):
            hours = int(job.recurrence.split("_", 1)[1])
            trigger = IntervalTrigger(hours=hours, start_date=job.schedule_at, timezone=ZoneInfo("Asia/Kolkata"))
            self.scheduler.add_job(self._run, trigger, args=[job.id], id=job_id, replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=300)
            job.next_run_at = self.scheduler.get_job(job_id).next_run_time
            return
        hour, minute = map(int, job.schedule_time.split(":"))
        args = {"hour": hour, "minute": minute, "timezone": ZoneInfo("Asia/Kolkata")}
        if job.recurrence == "weekly": args["day_of_week"] = job.day_of_week if job.day_of_week is not None else 0
        elif job.recurrence == "monthly": args["day"] = job.day_of_month or 1
        trigger = CronTrigger(**args)
        self.scheduler.add_job(self._run, trigger, args=[job.id], id=job_id, replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=300)
        job.next_run_at = self.scheduler.get_job(job_id).next_run_time
    def remove_all_report_jobs(self):
        for scheduled in list(self.scheduler.get_jobs()):
            if scheduled.id.startswith("report-job-"):
                self.scheduler.remove_job(scheduled.id)
    def _run(self, job_id):
        db = SessionLocal()
        try:
            WorkflowService().run_job(db, job_id)
            job = db.get(ReportJob, job_id)
            if job:
                scheduled = self.scheduler.get_job(f"report-job-{job_id}")
                job.next_run_at = None if job.recurrence == "once" else (scheduled.next_run_time if scheduled else None)
                db.commit()
        except Exception: pass
        finally: db.close()


_scheduler = SchedulerService()


def get_scheduler() -> SchedulerService:
    """Return the scheduler shared by application lifespan and API requests."""
    return _scheduler
