// CivicLens - Statutory Document PDF Export Engine
// Renders a generated complaint / RTI draft into a formatted, official-style
// PDF with a letterhead, reference footer and a faint watermark, then hands
// it off to the platform share sheet (mobile) or triggers a browser
// print/download (web).

import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';
import { Platform } from 'react-native';

/**
 * Escapes text for safe embedding inside HTML.
 */
function escapeHtml(str = '') {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/**
 * Converts plain-text letter content into HTML paragraphs, preserving
 * blank-line spacing between sections.
 */
function textToHtmlParagraphs(text = '') {
  return escapeHtml(text)
    .split(/\n{2,}/)
    .map((block) => `<p>${block.replace(/\n/g, '<br/>')}</p>`)
    .join('\n');
}

function buildDocumentHtml({
  title,
  docType,
  bodyText,
  refNumber,
  department,
  city,
  generatedOn,
}) {
  const deptName = department?.fullName || department?.name || 'Competent Public Authority';
  const deptCategory = department?.category ? escapeHtml(department.category) : '';

  return `
  <!DOCTYPE html>
  <html>
    <head>
      <meta charset="utf-8" />
      <style>
        @page { margin: 56px 48px; }
        * { box-sizing: border-box; }
        body {
          font-family: 'Times New Roman', Georgia, serif;
          color: #1a1a1a;
          position: relative;
          line-height: 1.55;
          font-size: 13px;
        }
        .watermark {
          position: fixed;
          top: 40%;
          left: 0;
          right: 0;
          text-align: center;
          font-size: 72px;
          font-weight: 700;
          color: rgba(53, 71, 168, 0.07);
          transform: rotate(-28deg);
          letter-spacing: 6px;
          z-index: -1;
        }
        .letterhead {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          border-bottom: 3px double #1e3a8a;
          padding-bottom: 10px;
          margin-bottom: 18px;
        }
        .brand {
          font-size: 19px;
          font-weight: 800;
          color: #1e3a8a;
          letter-spacing: 0.5px;
        }
        .brand small {
          display: block;
          font-size: 10px;
          font-weight: 500;
          color: #475569;
          letter-spacing: 1.5px;
          text-transform: uppercase;
          margin-top: 2px;
        }
        .meta {
          text-align: right;
          font-size: 10.5px;
          color: #334155;
        }
        .doc-title {
          text-align: center;
          font-size: 15px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 1px;
          margin: 6px 0 18px 0;
          color: #111827;
        }
        .doc-title .subline {
          display: block;
          font-size: 10.5px;
          font-weight: 500;
          text-transform: none;
          color: #64748b;
          margin-top: 3px;
        }
        .content p { margin: 0 0 12px 0; text-align: justify; }
        .footer {
          margin-top: 34px;
          padding-top: 10px;
          border-top: 1px solid #cbd5e1;
          font-size: 9.5px;
          color: #64748b;
          display: flex;
          justify-content: space-between;
        }
        .badge {
          display: inline-block;
          font-size: 9px;
          font-weight: 700;
          color: #1e3a8a;
          border: 1px solid #1e3a8a;
          border-radius: 3px;
          padding: 2px 6px;
          margin-top: 4px;
        }
      </style>
    </head>
    <body>
      <div class="watermark">CIVICLENS</div>

      <div class="letterhead">
        <div class="brand">
          CivicLens
          <small>National AI Civic &amp; Legal Copilot</small>
        </div>
        <div class="meta">
          Ref: ${escapeHtml(refNumber)}<br/>
          Generated: ${escapeHtml(generatedOn)}<br/>
          Jurisdiction: ${escapeHtml((city || 'National').toUpperCase())}
          ${deptCategory ? `<br/>Category: ${deptCategory}` : ''}
        </div>
      </div>

      <div class="doc-title">
        ${escapeHtml(title)}
        <span class="subline">Addressed to: ${escapeHtml(deptName)}</span>
      </div>

      <div class="content">
        ${textToHtmlParagraphs(bodyText)}
      </div>

      <div class="footer">
        <span>Drafted using CivicLens &mdash; Created by Team CodeX</span>
        <span class="badge">${escapeHtml(docType)}</span>
      </div>
    </body>
  </html>`;
}

/**
 * Generates a formatted PDF for a complaint/RTI draft and opens the native
 * share sheet (or browser download on web) so the user can save or send it.
 *
 * @returns {{ success: boolean, uri?: string, error?: string }}
 */
function buildRefAndTitle(docType) {
  const now = new Date();
  const refNumber = `CL-${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(
    now.getDate()
  ).padStart(2, '0')}-${Math.floor(1000 + Math.random() * 9000)}`;
  const title = docType.toLowerCase().includes('rti')
    ? 'Application under the Right to Information Act, 2005'
    : 'Statutory Civic Grievance Petition';
  return { refNumber, title, now };
}

export async function exportLetterToPdf({
  letterText,
  docType = 'Statutory Petition',
  department = null,
  city = '',
}) {
  if (!letterText || !letterText.trim()) {
    return { success: false, error: 'No document content to export.' };
  }

  const { refNumber, title, now } = buildRefAndTitle(docType);

  const html = buildDocumentHtml({
    title,
    docType,
    bodyText: letterText,
    refNumber,
    department,
    city,
    generatedOn: now.toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    }),
  });

  try {
    if (Platform.OS === 'web') {
      // expo-print's web implementation opens the browser print dialog,
      // from which the user can "Save as PDF".
      await Print.printAsync({ html });
      return { success: true };
    }

    const { uri } = await Print.printToFileAsync({ html, base64: false });

    const canShare = await Sharing.isAvailableAsync();
    if (canShare) {
      await Sharing.shareAsync(uri, {
        mimeType: 'application/pdf',
        dialogTitle: `${docType} - CivicLens`,
        UTI: 'com.adobe.pdf',
      });
    }

    return { success: true, uri, refNumber };
  } catch (err) {
    return { success: false, error: err?.message || 'PDF export failed.' };
  }
}

/**
 * Generates the same formatted PDF but returns it as base64 instead of
 * opening the share sheet — used to attach the petition to a real
 * automatically-sent email (see emailService.js). Not supported on web
 * (expo-print's web mode only supports the browser print dialog, not
 * base64 output) — email sending on web falls back to no attachment.
 */
export async function generatePdfBase64({ letterText, docType = 'Statutory Petition', department = null, city = '' }) {
  if (!letterText || !letterText.trim()) {
    return { success: false, error: 'No document content to export.' };
  }
  if (Platform.OS === 'web') {
    return { success: false, error: 'PDF-as-attachment isn\'t supported on web — use the Export PDF button and attach it manually if needed.' };
  }

  const { refNumber, title, now } = buildRefAndTitle(docType);
  const html = buildDocumentHtml({
    title,
    docType,
    bodyText: letterText,
    refNumber,
    department,
    city,
    generatedOn: now.toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' }),
  });

  try {
    const { base64 } = await Print.printToFileAsync({ html, base64: true });
    return { success: true, base64, filename: `CivicLens_${refNumber}.pdf` };
  } catch (err) {
    return { success: false, error: err?.message || 'PDF generation failed.' };
  }
}
