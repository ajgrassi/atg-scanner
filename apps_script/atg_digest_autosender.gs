/**
 * ATG Deal Digest auto-sender.
 *
 * Runs daily at 06:35 America/Chicago. Finds Gmail drafts whose subject
 * starts with `[ATG-DIGEST-AUTOSEND] ` (the magic prefix), strips the
 * prefix, sends the email, and removes the original draft.
 *
 * Pairs with the Claude Code Routine that creates the draft at 06:30.
 *
 * SETUP (one-time):
 *   1. Open https://script.google.com → New Project.
 *   2. Paste this entire file. Save (Ctrl-S, name it "ATG Digest Autosender").
 *   3. Run setupTrigger() once. Grant the requested permissions.
 *      (Gmail read/modify + send + trigger creation.)
 *   4. Verify with createTestDraft() then sendAtgDrafts() — should see the
 *      test draft moved to Sent within seconds.
 *
 * Why this exists:
 *   The built-in Claude Gmail connector can READ inbox + CREATE drafts,
 *   but cannot SEND. This script bridges that constraint without exposing
 *   a Gmail App Password to any external service.
 */

const MAGIC_PREFIX = '[ATG-DIGEST-AUTOSEND]';
const TRIGGER_NAME = 'sendAtgDrafts';
const TRIGGER_HOUR = 6;          // 06:35 America/Chicago
const TRIGGER_MINUTE = 35;
const TRIGGER_TIMEZONE = 'America/Chicago';

/**
 * Main: send any drafts that start with the magic prefix.
 */
function sendAtgDrafts() {
  const drafts = GmailApp.getDrafts();
  let sent = 0;
  let skipped = 0;
  const errors = [];

  for (const draft of drafts) {
    const message = draft.getMessage();
    const subject = message.getSubject() || '';
    if (!subject.startsWith(MAGIC_PREFIX + ' ')) {
      skipped += 1;
      continue;
    }

    const newSubject = subject.substring(MAGIC_PREFIX.length + 1).trim();
    const to = message.getTo();
    const cc = message.getCc();
    const bcc = message.getBcc();
    const htmlBody = message.getBody();
    const plainBody = message.getPlainBody();

    try {
      GmailApp.sendEmail(to, newSubject, plainBody, {
        cc: cc || undefined,
        bcc: bcc || undefined,
        htmlBody: htmlBody,
        name: 'ATG Deal Scanner',
      });
      draft.deleteDraft();
      sent += 1;
      Logger.log('SENT: %s -> %s', newSubject, to);
    } catch (e) {
      errors.push({subject: newSubject, to: to, error: e.toString()});
      Logger.log('ERROR sending %s: %s', newSubject, e);
    }
  }

  Logger.log('sendAtgDrafts complete. sent=%s skipped=%s errors=%s',
    sent, skipped, errors.length);
  return {sent, skipped, errors};
}

/**
 * Install the daily 06:35 Central trigger. Idempotent — clears any prior
 * trigger named TRIGGER_NAME first.
 */
function setupTrigger() {
  const existing = ScriptApp.getProjectTriggers();
  for (const t of existing) {
    if (t.getHandlerFunction() === TRIGGER_NAME) {
      ScriptApp.deleteTrigger(t);
      Logger.log('Removed prior trigger.');
    }
  }
  ScriptApp.newTrigger(TRIGGER_NAME)
    .timeBased()
    .everyDays(1)
    .atHour(TRIGGER_HOUR)
    .nearMinute(TRIGGER_MINUTE)
    .inTimezone(TRIGGER_TIMEZONE)
    .create();
  Logger.log('Trigger installed: daily %s:%s %s',
    TRIGGER_HOUR, TRIGGER_MINUTE, TRIGGER_TIMEZONE);
}

/**
 * Verification helper: create a test draft with the magic prefix, then
 * run sendAtgDrafts() to confirm the loop works end to end.
 */
function createTestDraft() {
  const me = Session.getActiveUser().getEmail();
  GmailApp.createDraft(
    me,
    MAGIC_PREFIX + ' ATG Autosender — test draft',
    'If you can read this, the autosender works.\n\n' +
    'Subject in your Sent folder will be unprefixed: '+
    '"ATG Autosender — test draft".',
    {
      htmlBody: '<p>If you can read this, the autosender works.</p>' +
                '<p>Subject in your Sent folder will be unprefixed: ' +
                '<code>ATG Autosender — test draft</code>.</p>',
      name: 'ATG Deal Scanner',
    }
  );
  Logger.log('Test draft created. Now run sendAtgDrafts().');
}

/**
 * Manual cleanup if you ever want to remove the daily trigger.
 */
function removeTrigger() {
  for (const t of ScriptApp.getProjectTriggers()) {
    if (t.getHandlerFunction() === TRIGGER_NAME) {
      ScriptApp.deleteTrigger(t);
      Logger.log('Removed trigger %s', t.getUniqueId());
    }
  }
}
