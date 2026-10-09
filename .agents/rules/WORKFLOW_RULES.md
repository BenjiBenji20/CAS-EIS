---
trigger: always_on
---

# WORKFLOW EXECUTION RULES & SAFETY CONSTRAINTS

### 1. STRICT READ-ONLY GIT POLICY
- **Permitted Git Commands:** Only non-mutating inspection commands are allowed (`git status`, `git log`, `git diff`, `git branch --list`).
- **Prohibited Git Commands:** Under no circumstances should you run commands that alter repository history, remotes, or state. Strictly prohibited: `git commit`, `git push`, `git pull`, `git merge`, `git rebase`, `git reset`, `git checkout -b`, `git stash pop`, `git cherry-pick`, or `git tag`.
- **Operator Authority:** Git staging, commits, branch management, and remote sync remain exclusively under human developer control.

### 2. MANDATORY ARTIFACT-FIRST PLANNING
- **No Premature Coding:** Never create, edit, or delete source files, configuration files, or database migrations before presenting a complete plan.
- **Structured Plan Scope:** Every architectural change, refactor, or new feature must first be documented in a structured artifact / plan specification detailing (not fixed to follow):
  1. Scope and target files affected.
  2. Report findings.
  3. Detailed implementation/recommendation/solution plan.
  4. Step-by-step implementation sequence.
  5. Potential regression risks and validation test plan.

### 3. EXPLICIT HUMAN APPROVAL GATE
- **Strict Halt:** After generating or updating an implementation plan artifact, halt execution immediately.
- **No Unsolicited Next Steps:** Do not begin coding based on assumptions. Prompt the user directly and wait for unambiguous, explicit confirmation (e.g., "Plan approved", "Proceed") before writing any implementation code.

### 4. MAINTAINING CODE CLEANLINESS
- **Delete the dead code:** During refactor, implementation or fix, if the blocks of code, function or class was not necessary to the system, report your action if going to delete it.
- **Refactor instead of creating a new:** If we are refactoring a code, refactor it. Do NOT create a new and dead code.