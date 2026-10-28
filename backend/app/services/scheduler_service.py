import calendar
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database.session import SessionLocal
from app.models.workflow import ReportJob
from app.services.workflow_service import WorkflowService

job_logger = logging.getLogger("app.jobs")
KOLKATA = ZoneInfo("Asia/Kolkata")
# The UI and stored day_of_week use Sunday=0 … Saturday=6, while APScheduler's
# numeric day_of_week starts at Monday=0. Day names avoid that ambiguity.
CRON_WEEKDAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")


class MonthlyLastDayTrigger(BaseTrigger):
    """Run monthly on the selected day, clamped to each month's last day."""

    def __init__(self, day: int, hour: int, minute: int, start_date=None, timezone=KOLKATA):
        self.day = max(1, min(int(day), 31))
        self.hour = int(hour)
        self.minute = int(minute)
        self.start_date = start_date.astimezone(timezone) if start_date and start_date.tzinfo else (start_date.replace(tzinfo=timezone) if start_date else None)
        self.timezone = timezone

    def get_next_fire_time(self, previous_fire_time, now):
        now = now.astimezone(self.timezone)
        if previous_fire_time is None:
            cursor = max(now, self.start_date) if self.start_date else now
        else:
            previous = previous_fire_time.astimezone(self.timezone)
            cursor = self._next_month(previous.replace(day=1))
        year, month = cursor.year, cursor.month
        while True:
            execution_day = min(self.day, calendar.monthrange(year, month)[1])
            candidate = datetime(year, month, execution_day, self.hour, self.minute, tzinfo=self.timezone)
            if candidate >= cursor and candidate >= now and (not self.start_date or candidate >= self.start_date):
                return candidate
            cursor = self._next_month(cursor.replace(day=1))
            year, month = cursor.year, cursor.month

    @staticmethod
    def _next_month(value):
        return value.replace(year=value.year + (1 if value.month == 12 else 0), month=1 if value.month == 12 else value.month + 1)

    def __repr__(self):
        return f"MonthlyLastDayTrigger(day={self.day}, hour={self.hour}, minute={self.minute})"


class SchedulerService:
    def __init__(self): self.scheduler = BackgroundScheduler(timezone=ZoneInfo("Asia/Kolkata"))
    def start(self): self.scheduler.start()
    def stop(self): self.scheduler.shutdown(wait=False)
    def sync_all(self):
        db = SessionLocal()
        try:
            for job in db.query(ReportJob).all(): self.sync_job(job)
            # sync_job updates next_run_at from the live trigger; persist it so
            # the UI shows the scheduler's real next execution.
            db.commit()
        finally: db.close()
    @staticmethod
    def build_trigger(job):
        """Return the APScheduler trigger for a job's saved schedule."""
        if job.recurrence == "once":
            return DateTrigger(run_date=job.schedule_at, timezone=KOLKATA)
        if job.recurrence == "every_2_minutes":
            return IntervalTrigger(minutes=2, start_date=job.schedule_at, timezone=KOLKATA)
        if job.recurrence.startswith("hourly_"):
            return IntervalTrigger(hours=int(job.recurrence.split("_", 1)[1]), start_date=job.schedule_at, timezone=KOLKATA)
        hour, minute = map(int, job.schedule_time.split(":"))
        if job.recurrence == "monthly":
            return MonthlyLastDayTrigger(day=job.day_of_month or 1, hour=hour, minute=minute, start_date=job.schedule_at, timezone=KOLKATA)
        # Execution Date is the first eligible run for every recurring type.
        args = {"hour": hour, "minute": minute, "timezone": KOLKATA, "start_date": job.schedule_at}
        if job.recurrence == "weekly":
            args["day_of_week"] = CRON_WEEKDAYS[job.day_of_week if job.day_of_week is not None else 0]
        return CronTrigger(**args)
    def sync_job(self, job):
        job_id = f"report-job-{job.id}"
        if not job.enabled:
            self.scheduler.remove_job(job_id) if self.scheduler.get_job(job_id) else None; return
        trigger = self.build_trigger(job)
        if job.recurrence == "once":
            self.scheduler.add_job(self._run, trigger, args=[job.id], id=job_id, replace_existing=True, max_instances=1, misfire_grace_time=300)
            job.next_run_at = job.schedule_at
            return
        self.scheduler.add_job(self._run, trigger, args=[job.id], id=job_id, replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=300)
        job.next_run_at = self.scheduler.get_job(job_id).next_run_time
    def remove_all_report_jobs(self):
        for scheduled in list(self.scheduler.get_jobs()):
            if scheduled.id.startswith("report-job-"):
                self.scheduler.remove_job(scheduled.id)
    def _run(self, job_id):
        db = SessionLocal()
        try:
            job = db.get(ReportJob, job_id)
            if not job or not job.enabled:
                return
            WorkflowService().run_job(db, job_id)
            job = db.get(ReportJob, job_id)
            if job:
                scheduled = self.scheduler.get_job(f"report-job-{job_id}")
                job.next_run_at = None if job.recurrence == "once" else (scheduled.next_run_time if scheduled else None)
                db.commit()
        except Exception as exc:
            job_logger.exception("Scheduled job %s failed: %s", job_id, exc)
        finally: db.close()


_scheduler = SchedulerService()


def get_scheduler() -> SchedulerService:
    """Return the scheduler shared by application lifespan and API requests."""
    return _scheduler
