"""The Hive Queen — orchestrates the worker agents for each analysis.

Pipeline (mirrors the hierarchical topology of the original
Digital Product Factory swarm, config/swarm-config.json):

    Queen
      ├─ triage worker      (sync, deterministic, always first)
      ├─ diagnosis worker   ┐ run concurrently — both only depend
      ├─ research worker    ┘ on the triage result
      └─ reporter worker    (assembles the final report)

Workers degrade gracefully: with ANTHROPIC_API_KEY set they enrich results
via Claude, without it the whole pipeline stays deterministic and free.
"""

import asyncio

from app.config import get_settings
from app.hive.workers import diagnosis, reporter, research, triage
from app.schemas import AnalysisReport, IssueInput, RepoScanReport
from app.services.github import fetch_open_issues


class HiveQueen:
    async def analyze_issue(self, issue: IssueInput) -> AnalysisReport:
        triage_result = triage.run(issue)

        diagnosis_result, research_brief = await asyncio.gather(
            diagnosis.run(issue, triage_result),
            research.run(issue, triage_result),
        )

        reply = reporter.build_reply(issue, triage_result, diagnosis_result)

        workers = ["triage", "diagnosis", "research", "reporter"]
        if get_settings().claude_enabled:
            workers.append("claude-enhancement")

        return AnalysisReport(
            issue_title=issue.title,
            issue_url=issue.url,
            triage=triage_result,
            diagnosis=diagnosis_result,
            research_brief=research_brief,
            suggested_reply=reply,
            workers_used=workers,
        )

    async def scan_repository(self, owner: str, repo: str, limit: int = 5) -> RepoScanReport:
        issues = await fetch_open_issues(owner, repo, limit)
        settings = get_settings()
        semaphore = asyncio.Semaphore(settings.max_concurrent_analyses)

        async def analyze_bounded(issue: IssueInput) -> AnalysisReport:
            async with semaphore:
                return await self.analyze_issue(issue)

        # asyncio.timeout() would read better but only exists on 3.11+, and the project
        # supports 3.10 (see requires-python and the CI matrix).
        reports = await asyncio.wait_for(
            asyncio.gather(*(analyze_bounded(issue) for issue in issues)),
            timeout=settings.scan_timeout_seconds,
        )

        connectivity_reports = [r for r in reports if r.triage.is_connectivity_issue]
        return RepoScanReport(
            owner=owner,
            repo=repo,
            issues_scanned=len(issues),
            connectivity_issues_found=len(connectivity_reports),
            reports=list(reports),
        )
