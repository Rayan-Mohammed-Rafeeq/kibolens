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

The standard image leaves the native libvirt binding out deliberately so a
missing or incompatible hypervisor development header cannot block KiboLens.
To opt into the binding on a Linux host, set `KIBOLENS_INSTALL_LIBVIRT=true`
in the server-local environment before the backend build. The image build
prints the resolved `libvirt-dev` version and installs `libvirt-python==12.8.0`.
The observer still reports an honest empty/unavailable VM inventory when the
binding or `/var/run/libvirt` connection is absent.

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
creates one persistent incident. The configured incident recipient receives
the Resend notification. Open the incident from **Incidents** and confirm the
evidence timeline.

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
