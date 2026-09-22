// Ported from legacy-prototype/src/screens/DocumentScannerScreen.js (upload card with camera/gallery
// actions, status badges). The zip's per-document-type OCR chips assumed a client-side vision model
// (analyzeDocumentImage) with per-category prompts; our real backend runs the same OCR+indexing
// pipeline regardless of category, so those chips are dropped rather than kept as non-functional UI.
import React, { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { AppButton, Body, ErrorBanner, InfoBanner, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { DocumentRecord } from '../src/api/types.ts';
import { pickPhotos, takePhoto } from '../src/hooks/usePhotos.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { useTheme } from '../src/theme/ThemeContext.tsx';
import { ApiError } from '../src/api/errors.ts';
import { fontFamily, radius, shadow, spacing } from '../src/theme.ts';

export default function Documents() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const STATUS_LABEL: Record<string, { text: string; color: string }> = {
    uploaded: { text: 'Queued', color: colors.textMuted },
    processing: { text: 'Extracting & indexing…', color: colors.warn },
    ready: { text: 'Ready - searchable by Civic Saathi', color: colors.ok },
    failed: { text: 'Failed', color: colors.bad },
  };
  const [items, setItems] = useState<DocumentRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notConfigured, setNotConfigured] = useState(false);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try { setItems((await endpoints.listDocuments()).items); }
    catch (e: any) {
      if (e instanceof ApiError && e.isNotConfigured) { setNotConfigured(true); setItems([]); return; }
      setError(e?.message ?? 'Could not load your documents.'); setItems([]);
    }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!items?.some((d) => d.status === 'uploaded' || d.status === 'processing')) return;
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [items, load]);

  async function upload(kind: 'camera' | 'library') {
    setUploading(true); setError(null);
    try {
      const files = kind === 'camera' ? [await takePhoto()].filter(Boolean) as any[] : await pickPhotos();
      for (const f of files) await endpoints.uploadDocument(f);
      await load();
    } catch (e: any) {
      if (e instanceof ApiError && e.isNotConfigured) setNotConfigured(true);
      else setError(e?.message ?? 'Could not upload the document.');
    } finally { setUploading(false); }
  }

  return (
    <Screen>
      <Text style={{ fontFamily: fontFamily.displayBold, fontSize: 20, color: colors.text }}>📄 {t('nav.documents')}</Text>
      <Body soft>Scan notices, receipts, FIR copies or bills - once processed, Civic Saathi can cite them when you ask a question.</Body>
      {notConfigured ? <InfoBanner tone="warn" message="Document processing is not configured on this server yet. Ask an administrator to enable it." /> : null}
      {error ? <ErrorBanner message={error} onRetry={load} /> : null}

      <View style={[{ borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, alignItems: 'center', backgroundColor: colors.card, borderColor: colors.border }, shadow.sm]}>
        <View style={{ alignItems: 'center', paddingVertical: 16 }}>
          <Ionicons name="document-scanner-outline" size={48} color={colors.primary} />
          <Text style={{ fontFamily: fontFamily.bodyExtraBold, fontSize: 14, marginTop: 10, color: colors.text }}>Snap or Upload an Official Document</Text>
          <Text style={{ fontSize: 11, textAlign: 'center', marginTop: 4, paddingHorizontal: 20, color: colors.textMuted }}>Traffic challans, municipal notices, FIR copies, utility bills, or a photo of the civic problem itself</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 12, width: '100%' }}>
          <View style={{ flex: 1 }}><AppButton label="Camera" icon="📷" onPress={() => upload('camera')} busy={uploading} disabled={notConfigured} /></View>
          <View style={{ flex: 1 }}><AppButton label="Gallery" kind="secondary" icon="🖼️" onPress={() => upload('library')} busy={uploading} disabled={notConfigured} /></View>
        </View>
      </View>

      {items === null ? <Loading label={t('msg.loading')} /> : items.length === 0 && !notConfigured ? (
        <Body soft>No documents yet - the ones you scan will appear here with their processing status.</Body>
      ) : items.map((d) => {
        const st = STATUS_LABEL[d.status] ?? { text: d.status, color: colors.textMuted };
        return (
          <View key={d.id} style={[{ borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, backgroundColor: colors.card, borderColor: colors.border }, shadow.sm]}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text style={{ fontWeight: '700', flex: 1, color: colors.text }} numberOfLines={1}>{d.name}</Text>
              <Text style={{ color: st.color, fontSize: 12, fontWeight: '700' }}>{st.text}</Text>
            </View>
            <Body soft>{(d.size / 1024).toFixed(0)} KB · {d.mime}{d.chunk_count ? ` · ${d.chunk_count} chunks indexed` : ''}</Body>
            {d.status === 'failed' ? (
              <>
                {d.error ? <ErrorBanner message={d.error} /> : null}
                <AppButton label="Retry" kind="secondary" onPress={async () => { await endpoints.retryDocument(d.id); await load(); }} />
              </>
            ) : null}
          </View>
        );
      })}
    </Screen>
  );
}
