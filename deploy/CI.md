# CI / auto-deploy setup

`.github/workflows/deploy.yml` deploys PocketBroker automatically: every push to
`main` (and the manual **Run workflow** button) makes a GitHub runner SSH into the
VPS and run `deploy.sh`. One-time setup below — all of it is on **your** side
(GitHub account + the VPS); the repo itself needs no further changes.

## 1. Dedicated deploy keypair

Generate a key used **only** for deploys (don't reuse a personal key):

```bash
ssh-keygen -t ed25519 -f deploy_key -N "" -C "github-actions-deploy"
```

Authorize the **public** key on the VPS for user `mvp`:

```bash
ssh-copy-id -i deploy_key.pub deploy@app.example.com
# or manually append deploy_key.pub to /home/deploy/.ssh/authorized_keys
```

## 2. GitHub repository secrets

Settings → Secrets and variables → Actions → **New repository secret**:

| Secret        | Value                                              |
|---------------|----------------------------------------------------|
| `VPS_HOST`    | `app.example.com`                          |
| `VPS_USER`    | `mvp`                                               |
| `VPS_SSH_KEY` | full contents of the **private** `deploy_key` file |
| `VPS_PORT`    | only if SSH isn't on 22                             |

Or with the `gh` CLI:

```bash
gh secret set VPS_HOST  --body "app.example.com"
gh secret set VPS_USER  --body "mvp"
gh secret set VPS_SSH_KEY < deploy_key
```

Delete the local `deploy_key` / `deploy_key.pub` afterwards.

## 3. Passwordless sudo for the service restart

`deploy.sh` ends with `sudo systemctl restart pocketbroker-api`. Over a
non-interactive SSH session a password prompt would hang the deploy, so grant
NOPASSWD for exactly that one command. On the VPS:

```bash
echo 'mvp ALL=(root) NOPASSWD: /usr/bin/systemctl restart pocketbroker-api' \
  | sudo tee /etc/sudoers.d/pocketbroker
sudo chmod 440 /etc/sudoers.d/pocketbroker
sudo visudo -c   # validate
```

## 4. Finish the one-time server bring-up

The restart step only works once the `pocketbroker-api` systemd unit exists.
Complete **steps 4–6 of [`SETUP.md`](SETUP.md)** (install+enable the unit, apply
nginx, certbot) before relying on auto-deploy. Until then a deploy still pulls,
builds, rsyncs the frontend, and runs migrations — only the restart fails.

## Verify

1. Actions tab → **Deploy to VPS** → **Run workflow** (manual `workflow_dispatch`).
2. Watch the log stream `deploy.sh` output, ending at `App live at https://app.example.com`.
3. `curl -s https://app.example.com/api/health` → `{"status":"ok"}`.

After that, any push to `main` redeploys automatically.
