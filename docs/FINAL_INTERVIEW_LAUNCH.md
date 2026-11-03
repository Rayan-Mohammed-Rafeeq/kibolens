# KiboLens final interview launch

This runbook uses the dedicated `interview-demo` Failure Lab scenario. It is
isolated, capped at 0.1 CPU / 32 MiB / 10 PIDs, has no production credentials,
uses an internal network, and never runs against a Kibo production service.

## 1. Update Kibo from GitHub

Run on Kibo from `/home/sysadmin/kibolens` after confirming the working tree is
clean and any server-local Compose customization is preserved:

```bash
git status --short --branch
git fetch origin
git pull --ff-only origin main
```

If `git pull --ff-only` reports local changes or a conflict, stop and preserve
those changes before continuing. Never reset the server tree.

## 2. Start KiboLens and monitoring

```bash
cd /home/sysadmin/kibolens
docker compose --env-file .env -f deployment/docker-compose.yml build backend frontend
docker compose --env-file .env -f deployment/docker-compose.yml up -d backend frontend
docker compose --env-file .env -f deployment/docker-compose.yml exec backend alembic heads
docker compose --env-file .env -f deployment/docker-compose.yml exec backend alembic current
docker compose --env-file .env -f deployment/docker-compose.yml exec backend alembic upgrade head
docker compose --env-file .env -f deployment/docker-compose.yml --profile monitoring up -d
docker compose --env-file .env -f deployment/docker-compose.yml ps
```

The standard backend image installs the native libvirt binding and the Compose
configuration mounts the host's read-only `/var/run/libvirt` socket. The image
build prints the resolved `libvirt-dev` version, compiles `libvirt-python`
from source with Python build tooling, imports the binding as a build check,
and installs `libvirt-python==12.8.0`. The production Compose
file always builds with VM support; only a direct development Docker build may
explicitly pass `--build-arg INSTALL_LIBVIRT=false`.

The deployment host must also run libvirt and expose `qemu:///system`; for a
Debian/Ubuntu host, install and start it before rebuilding the backend:

```bash
sudo apt-get update
sudo apt-get install -y libvirt-daemon-system qemu-kvm
sudo systemctl enable --now libvirtd

# Configure the host socket's numeric group ID in .env. Do not copy a group
# name or assume the host GID matches a container group.
stat -c '%g' /var/run/libvirt/libvirt-sock
# KIBOLENS_LIBVIRT_SOCKET_GID=<the number printed above>
```

Then rebuild and restart the backend so the binding is installed and the host
socket is mounted:

```bash
docker compose --env-file .env -f deployment/docker-compose.yml build backend
docker compose --env-file .env -f deployment/docker-compose.yml up -d backend
```

The backend passes `KIBOLENS_LIBVIRT_SOCKET_GID` as a supplementary numeric
group, so a host using a nonstandard libvirt group remains accessible without
changing container group IDs. A missing socket or unconfigured hypervisor is
reported as `unconfigured` and the UI shows **No virtual machines detected.**
An available daemon with no domains shows the same empty state. A socket-present
connection or permission failure remains `unavailable` with an actionable
diagnostic. Once libvirt is installed and authorized, the next inventory poll
discovers domains automatically.

Build the isolated lab image once; this does not start a scenario:

```bash
docker compose --env-file .env -f deployment/failure-lab/docker-compose.yml --profile lab config --services
docker compose --env-file .env -f deployment/failure-lab/docker-compose.yml --profile lab build interview-demo
```

## 3. Open and verify the application

Open the configured public KiboLens URL, sign in with the normal administrator
authentication flow, then verify:

1. **Overview** shows current Prometheus host metrics.
2. **Infrastructure** shows Docker containers and the optional libvirt VM list.
3. If no libvirt domains exist, the VM panel must show the honest empty state.
4. **Settings** shows the signed-in account email, verification state, incident
   notification toggle, minimum severity and recovery-notification preference.

Incident email delivery uses the verified account email and the configured
Resend sender. No recipient is accepted from the browser. Verify the account
email through Settings if needed, enable notifications, and use **Send test to
my account email**. Failed Resend deliveries remain persisted for retry; a
notification is sent once for a new incident or severity escalation rather
than on every monitoring poll.

## 4. Run the controlled failure demonstration

Open **Failure Lab / Demo Simulation** and select **interview demo**. Click
**Start**. The API starts `kibolens-lab-interview-demo` in the internal lab
network. It writes real logs and exits with code `42`.

Verify from the Kibo shell if needed:

```bash
docker ps -a --filter name=kibolens-lab-interview-demo
docker inspect kibolens-lab-interview-demo --format '{{.State.Status}} exit={{.State.ExitCode}}'
docker logs kibolens-lab-interview-demo
docker events --since 2m --until now --filter container=kibolens-lab-interview-demo
```

The Docker observer polls the event, correlates the stable lab fingerprint,
captures the stopped container's ID, exit code, restart state and logs, and
creates one persistent incident. If **Send demo email to my account email** is
enabled, the verified account receives a clearly labelled `[SIMULATED]`
notification. The lab result reports whether the incident was created and
whether email delivery was sent, pending, not configured or failed. Open the
incident from **Incidents** and confirm the evidence timeline.

## 5. Investigate with AI

Open the incident and click **Investigate**. Use a question such as:

```text
Explain why the interview demo container failed. Use the actual Docker exit
code and logs, current Prometheus evidence, and any relevant indexed runbook.
Separate observed evidence from probable conclusions, recommend a safe fix,
and state how recovery should be verified.
```

The investigation path is:

```text
Incident context → LangGraph → Prometheus/Docker/Qdrant evidence
→ LangChain CloudRouterChatModel → Gemini → Groq → OpenRouter free fallback
→ persisted assistant response
```

No paid model or Ollama fallback is used in cloud mode.

## 6. Recover the same incident

On the `interview-demo` card click **Recover**. KiboLens replaces the failed
lab container with the same logical scenario in healthy mode. It stays alive,
and the Docker `start` event resolves the same incident fingerprint.

Verify:

```bash
docker inspect kibolens-lab-interview-demo --format '{{.State.Status}} exit={{.State.ExitCode}}'
docker logs kibolens-lab-interview-demo
```

The incident should show the recovery timeline and a recovery email should be
recorded/sent. Failed Resend deliveries are retried by the bounded notification
retry loop.

## 7. Reset and stop safely

Use **Reset lab and close demo incidents** in Failure Lab. It removes only
containers labeled `kibolens.lab=true` and closes only lab/simulation incidents.
It does not stop or remove Kibo production containers or volumes.

```bash
docker compose --env-file .env -f deployment/failure-lab/docker-compose.yml --profile lab config --quiet
docker compose --env-file .env -f deployment/docker-compose.yml ps
```

Do not run `docker compose down -v`.
