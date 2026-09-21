import React, { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { AppButton, Body, Card, EmptyState, ErrorBanner, H1, InfoBanner, Loading, Screen } from '../src/components/ui.tsx';
import { endpoints } from '../src/api/instance.ts';
import type { DocumentRecord } from '../src/api/types.ts';
import { pickPhotos, takePhoto } from '../src/hooks/usePhotos.ts';
import { useI18n } from '../src/i18n/I18nContext.tsx';
import { useTheme } from '../src/theme/ThemeContext.tsx';
import { ApiError } from '../src/api/errors.ts';

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
  // Documents finish processing in the background - poll gently while any are still in flight.
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
      <H1>{t('nav.documents')}</H1>
      <Body soft>Scan a notice, receipt or previous reply. Once processed, Civic Saathi can cite it when you ask a question.</Body>
      {notConfigured ? <InfoBanner tone="warn" message="Document processing is not configured on this server yet. Ask an administrator to enable it." /> : null}
      {error ? <ErrorBanner message={error} onRetry={load} /> : null}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <AppButton label="Scan with camera" kind="secondary" onPress={() => upload('camera')} busy={uploading} disabled={notConfigured} />
        <AppButton label="Choose from gallery" kind="secondary" onPress={() => upload('library')} busy={uploading} disabled={notConfigured} />
      </View>

      {items === null ? <Loading label={t('msg.loading')} /> : items.length === 0 && !notConfigured ? <EmptyState message="No documents yet." /> : items.map((d) => {
        const st = STATUS_LABEL[d.status] ?? { text: d.status, color: colors.textMuted };
        return (
          <Card key={d.id}>
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
          </Card>
        );
      })}
    </Screen>
  );
}
