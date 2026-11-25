"""Verify an integration receipt and trusted GitHub CI for the exact delivery SHA."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import urlencode
from zipfile import BadZipFile, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release
from cdx_common import SHA, Refused, atomic_write, git, json_bytes, load_project, read_json, report_error, stamp, state_path
from cdx_work import integration_receipt


REMOTE = re.compile(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
                    r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?")
WORKFLOW = re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml")
EVENTS = {"push", "merge_group", "workflow_dispatch"}


def github(endpoint, *, pages=False):
    command = ["gh", "api", "--hostname", "github.com", endpoint]
    if pages:
        command.extend(("--paginate", "--slurp"))
    response = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    if response.returncode:
        raise Refused(f"Unable to verify GitHub Actions evidence at {endpoint.split('?')[0]}")
    return json.loads(response.stdout)


def validate_policy(policy):
    if not isinstance(policy, dict):
        raise Refused("Configure cdx_release_ci in director_work.json")
    workflow, signature, jobs = (policy.get(key) for key in ("workflow", "workflow_sha256", "jobs"))
    if not isinstance(workflow, str) or not WORKFLOW.fullmatch(workflow):
        raise Refused("Pin a GitHub workflow file in cdx_release_ci.workflow")
    if not isinstance(signature, str) or not re.fullmatch(r"[a-f0-9]{64}", signature):
        raise Refused("Pin the trusted workflow's exact SHA-256")
    if (not isinstance(jobs, list) or not jobs or not all(isinstance(job, str) and job.strip() for job in jobs) or
            len(jobs) != len(set(jobs))):
        raise Refused("Pin the required GitHub job names")
    return workflow, signature, set(jobs)


def check_ci(repo, slug, head, run_id, policy, artifact_sha256=None, *, branch=None):
    workflow, signature, required = validate_policy(policy)
    if hashlib.sha256(git(repo, "show", f"{head}:{workflow}", raw=True)).hexdigest() != signature:
        raise Refused("The delivery SHA does not contain the trusted workflow")
    prefix = f"repos/{slug}/actions"
    run_url = f"{prefix}/runs/{run_id}"
    run = github(run_url)
    owner = (run.get("repository") or {}).get("full_name", "")
    source = (run.get("head_repository") or {}).get("full_name", "")
    workflow_id, attempt = run.get("workflow_id"), run.get("run_attempt")
    scope = branch or run.get("head_branch")
    if (run.get("id") != run_id or run.get("head_sha") != head or
            owner.casefold() != slug.casefold() or source.casefold() != slug.casefold() or
            run.get("path", "").split("@", 1)[0] != workflow or run.get("event") not in EVENTS or
            run.get("status") != "completed" or run.get("conclusion") != "success" or
            not isinstance(scope, str) or not scope or run.get("head_branch") != scope or
            type(attempt) is not int or attempt < 1 or type(workflow_id) is not int or workflow_id < 1):
        raise Refused("CI run must attest to the exact SHA, trusted workflow and repository")
    jobs_url = f"{run_url}/attempts/{attempt}/jobs?per_page=100"
    jobs = [job for page in github(jobs_url, pages=True) for job in page["jobs"]]
    for name in required:
        found = [job for job in jobs if job.get("name") == name]
        if (len(found) != 1 or found[0].get("status") != "completed" or
                found[0].get("conclusion") != "success" or found[0].get("head_sha") != head):
            raise Refused(f"Missing passing job at this exact SHA: {name}")
    query = urlencode({"head_sha": head, "branch": scope, "per_page": 100})
    latest_url = f"{prefix}/workflows/{workflow_id}/runs?{query}"
    current = github(latest_url)
    eligible = [row for row in current["workflow_runs"] if row.get("event") in EVENTS and
                row.get("head_sha") == head and row.get("head_branch") == scope]
    latest = max(eligible, key=lambda row: (row["created_at"], row["id"]), default={})
    if (latest.get("id") != run_id or latest.get("run_attempt") != attempt or latest.get("status") != "completed" or
            latest.get("conclusion") != "success"):
        raise Refused(f"A newer GitHub CI run or attempt on {scope} supersedes this evidence")
    evidence = {"repository": slug, "head": head, "workflow": workflow, "workflow_sha256": signature,
                "branch": scope, "event": run["event"], "run_id": run_id, "run_attempt": attempt,
                "jobs": sorted(required), "url": run.get("html_url")}
    artifact = policy.get("artifact_name")
    if artifact is not None or artifact_sha256:
        if (not isinstance(artifact, str) or not artifact.strip() or
                not re.fullmatch(r"[a-f0-9]{64}", artifact_sha256 or "")):
            raise Refused("Pin an artifact name in cdx_release_ci and provide its SHA-256")
        artifact = artifact.replace("{attempt}", str(attempt))
        if attempt > 1 and not artifact.endswith(f"-attempt-{attempt}"):
            raise Refused("Use an artifact_name template ending with -attempt-{attempt} for reruns")
        url = f"{run_url}/artifacts?per_page=100"
        artifacts = [item for page in github(url, pages=True) for item in page["artifacts"]
                     if item.get("name") == artifact and item.get("expired") is False]
        if len(artifacts) != 1 or artifacts[0].get("digest") != f"sha256:{artifact_sha256}":
            raise Refused("No unique build artifact with the expected GitHub digest")
        evidence["artifact"] = {"id": artifacts[0]["id"], "name": artifact, "sha256": artifact_sha256}
    return evidence


def stream_digest(handle):
    digest = hashlib.sha256()
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def verify_delivery_archive(proof, receipt, archive_file, policy):
    members = {row["order"]: row["artifact"] for row in proof["members"] if row.get("artifact")}
    archive_sha = receipt.get("artifact", {}).get("sha256")
    if archive_file is None:
        if any(digest != archive_sha for digest in members.values()):
            raise Refused("Provide the attested CI archive and artifact_members for the accepted build outputs")
        return {order: {"sha256": digest} for order, digest in members.items()}
    if not archive_sha:
        raise Refused("An archive needs the matching GitHub CI artifact attestation")
    paths = policy.get("artifact_members", {})
    if not isinstance(paths, dict):
        raise Refused("artifact_members must map work order IDs to paths inside the CI archive")
    with archive_file.open("rb") as raw:
        if stream_digest(raw) != archive_sha:
            raise Refused("The downloaded CI archive does not match its attested SHA-256")
        raw.seek(0)
        with ZipFile(raw) as archive:
            files = [info.filename for info in archive.infolist() if not info.is_dir()]
            result = {}
            for order, accepted in members.items():
                name = paths.get(order)
                if name is None and accepted == archive_sha:
                    result[order] = {"sha256": accepted}
                    continue
                if (not isinstance(name, str) or not name or "\\" in name or PurePosixPath(name).is_absolute() or
                        any(part in ("", ".", "..") for part in name.split("/")) or files.count(name) != 1):
                    raise Refused(f"{order} needs one unique artifact_members path in the CI archive")
                with archive.open(name) as item:
                    if stream_digest(item) != accepted:
                        raise Refused(f"{order} artifact differs from the accepted build output")
                result[order] = {"path": name, "sha256": accepted}
    return result


def check_delivery(repo, state, job, args, policy):
    head = job.head()
    if not SHA.fullmatch(head) or head != args.head:
        raise Refused("Release HEAD changed or differs from the requested delivery SHA")
    push = REMOTE.fullmatch(git(repo, "remote", "get-url", "--push", job.remote))
    fetch = REMOTE.fullmatch(git(repo, "remote", "get-url", job.remote))
    if (not push or not fetch or push[1] != fetch[1] or
            (job.config.get("gh_repo") and job.config["gh_repo"] != push[1])):
        raise Refused("Release fetch, push and GitHub target must agree")
    slug = push[1]
    remote_base = git(repo, "rev-parse", f"refs/remotes/{job.remote}/{job.branch}")
    landed = head if remote_base == head else None
    if not args.push_only and landed is None:
        raise Refused("Land the verified SHA first. Use --push-only or the repository merge workflow, then use target CI.")
    proof = integration_receipt(repo, state, args.integration, landed_head=landed)
    if proof["outcome"] != "PASS":
        raise Refused(f"Integration {args.integration} is {proof['outcome']}")
    if remote_base not in (proof["base"], landed) or proof["target"] not in (
            f"refs/remotes/{job.remote}/{job.branch}", f"refs/heads/{job.branch}"):
        raise Refused("Integration was not based on the current release target")
    if proof["head"] != head:
        if git(repo, "rev-parse", f"{proof['head']}^{{tree}}") != git(repo, "rev-parse", f"{head}^{{tree}}"):
            raise Refused("Actual delivery tree differs from the verified integration")
        git(repo, "merge-base", "--is-ancestor", proof["base"], head)
    branch = job.branch
    if args.push_only and landed is None:
        branch = policy.get("candidate_branch") or git(repo, "branch", "--show-current")
        if not isinstance(branch, str) or not branch.strip() or branch == job.branch:
            raise Refused("Pin the candidate Git branch for the pre-push CI")
        git(repo, "check-ref-format", f"refs/heads/{branch}")
    receipt = check_ci(repo, slug, head, args.ci_run, policy, args.artifact, branch=branch)
    outputs = verify_delivery_archive(proof, receipt, args.archive, policy)
    if (job.head() != head or integration_receipt(repo, state, args.integration, landed_head=landed)["outcome"] != "PASS"):
        raise Refused("Delivery evidence changed during verification")
    job.delivery_head, job.delivery_base = head, proof["base"] if args.push_only else head
    if not args.push_only:
        ci_url = f"https://github.com/{slug}/actions/runs/{args.ci_run}"
        job.notes += f"\n\n已驗證交付提交 `{head}`。 [目標分支 CI]({ci_url})\n"
    proof_path = state_path(state, "delivery", head, f"{args.ci_run}-{receipt['run_attempt']}.json")
    evidence = dict(receipt, integration=args.integration, checked=stamp(), integration_head=proof["head"],
                    stage="push" if args.push_only else "publish", outputs=outputs)
    atomic_write(proof_path, json_bytes(evidence))
    print("CDX_DELIVERY " + json.dumps(dict(evidence, receipt=str(proof_path)), ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--integration", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--ci-run", required=True, type=int)
    parser.add_argument("--artifact", help="SHA-256 of the named GitHub build archive")
    parser.add_argument("--archive", type=Path, help="downloaded CI ZIP containing PO-accepted build outputs")
    parser.add_argument("--push-only", action="store_true", help="check candidate CI and push without creating a release")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not SHA.fullmatch(args.head) or args.ci_run < 1:
            raise Refused("Supply a complete delivery SHA and a positive GitHub run ID")
        root, state, _ = load_project(args.repo)
        config = state_path(state, "director_work.json")
        policy = read_json(config).get("cdx_release_ci")
        validate_policy(policy)
        command = ["--repo", str(root), "--config", str(config)]
        if args.execute:
            command.append("--execute")
        return release.main(command, delivery_check=lambda job: check_delivery(root, state, job, args, policy),
                            push_only=args.push_only)
    except (OSError, ValueError, RuntimeError, KeyError, BadZipFile, subprocess.SubprocessError) as error:
        return report_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
