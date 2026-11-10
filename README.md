# Perathos Gate approval for GitHub Actions

Stop a workflow until a named person approves **this exact run** on their phone with a
passkey. The job continues only on approval, and the signed receipt is attached to the run so
anyone can check it later, offline.

```yaml
- name: Approval from a person, with a passkey
  id: gate
  uses: perathos-protocol/gate-action@v1
  with:
    summary: Deploy api to production
    target: production
    api-key: ${{ secrets.PERATHOS_GATE_API_KEY }}
    gate-key: ${{ vars.PERATHOS_GATE_KEY }}
    approver-keys: ${{ vars.PERATHOS_GATE_APPROVERS }}

- name: Deploy
  run: ./deploy.sh   # runs only if a pinned approver said yes
```

## What happens

1. The step asks a [Perathos Gate](https://github.com/perathos-protocol/perathos-gate) server
   for an approval. The request names the repository, commit, workflow, run, attempt and actor.
2. The Gate notifies the organisation's approvers (Web Push, or a Slack-compatible webhook).
   An approver reads the request and approves or denies it with a passkey (Face ID,
   fingerprint or PIN).
3. The step checks the receipt before it lets the job continue: the Gate's signature against
   the key you pinned, the approver's passkey signature, that the passkey is one you pinned,
   and that the approval is for this run and not another.
4. The receipt is uploaded as an artifact and summarised on the run page.

Denied, no decision in time, a receipt that fails a check, or an unreachable Gate all fail
the step. It never continues on doubt.

## Why not GitHub's required reviewers?

Environment protection rules record that a GitHub account clicked "Approve". That is a
useful control and you can keep it. This adds evidence that stands on its own:

- The approval is a WebAuthn signature with user verification, over a hash of the exact
  request and the decision. It is not a session click.
- The receipt verifies offline against keys you pinned, without GitHub and without the Gate
  server being reachable.
- It is bound to the commit and run. An approval for one run cannot be reused for another,
  including a re-run (the attempt number is part of what was approved).

## Setup

You need a Gate server (self-hosted, or an organisation on a hosted one), an organisation API
key, and at least one enrolled approver. See the
[perathos-gate README](https://github.com/perathos-protocol/perathos-gate#readme).

| Where | Name | Value |
|---|---|---|
| Repository secret | `PERATHOS_GATE_API_KEY` | The organisation API key (`pgk_...`) |
| Repository variable | `PERATHOS_GATE_KEY` | The Gate's signing key: `verify_key` from `https://<gate>/.well-known/perathos-gate.json` |
| Repository variable | `PERATHOS_GATE_APPROVERS` | Output of `perathos gate approvers --keys` on a machine where you ran `perathos gate trust <receipt>` |

The two variables are public keys. They are not secret, and pinning them in the repository is
the point: the workflow then trusts those keys, not whatever a server says.

## Inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `summary` | yes | | What the approver reads |
| `api-key` | yes | | Organisation API key; pass a secret |
| `gate-key` | yes | | Pinned Gate signing key (hex) |
| `approver-keys` | no | empty | Pinned approver passkey public keys, comma-separated. Without it the step warns, because the Gate server then decides who counts as an approver |
| `gate-url` | no | `https://gate.perathos.com` | Gate server |
| `target` | no | empty | The thing acted on |
| `detail` | no | repository, commit, run, actor | Extra text for the approver |
| `wait-seconds` | no | `900` | How long the job waits (1 to 3600) |
| `ttl-seconds` | no | `1800` | How long the request stays approvable (60 to 3600) |
| `receipt-path` | no | `perathos-approval-receipt.json` | Where the receipt is written |
| `upload-receipt` | no | `true` | Upload the receipt as an artifact |
| `perathos-version` | no | `1.4.3` | Version of the `perathos` package to install |

Outputs: `receipt-path`, `receipt-hash`, `approver`.

## Checking a receipt later

Download the artifact from the run, then:

```bash
pip install perathos
perathos gate verify perathos-approval-receipt.json --gate-key <the pinned Gate key>
```

## What this does and does not show

Evidence, not a guarantee.

- It shows that a passkey enrolled under the approver's name, and pinned by you, signed an
  approval of this request, with a biometric or PIN check, at the time the Gate recorded.
- It does not show that the approver understood what they approved, or which device holds the
  passkey (synced passkeys are accepted and no attestation is requested).
- The approver sees the text in `summary` and `detail`. The approval is bound to the commit
  and run, not to what later steps in the job do. Put the gate immediately before the step it
  protects, and keep the job's later steps in the same reviewed workflow file.
- Someone who can edit the workflow file, or change the repository variables, can remove the
  gate or pin other keys. Protect both with branch protection and restricted repository
  settings.
- The approve link is deliberately not printed in the job log, since logs of public
  repositories are public. Approvers get it by notification.
- A `pull_request` workflow from a fork has no access to secrets, so the step fails there.
  That is the safe outcome.

Full threat model:
[perathos/docs/THREAT_MODEL.md](https://github.com/perathos-protocol/perathos/blob/main/docs/THREAT_MODEL.md).

## Demo

This repository gates itself. [`demo.yml`](.github/workflows/demo.yml) is a manual workflow
with a stand-in deploy step; the approval, receipt and verification in it are real.

## Licence

MIT.
