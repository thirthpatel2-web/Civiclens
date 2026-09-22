// WEB ONLY. react-native-maps is native-only (it wraps Google/Apple Maps SDKs) and has no web
// implementation, so metro.config.js aliases the package to this file for platform === 'web'.
// It renders an honest placeholder instead of a map - it never pretends to show real geography.
// Native builds are untouched and still use the real react-native-maps.
import React from 'react';
import { Text, View } from 'react-native';

type AnyProps = Record<string, unknown> & { children?: React.ReactNode };

export default function MapView({ children, style }: AnyProps & { style?: unknown }) {
  return (
    <View
      style={[
        { flex: 1, minHeight: 320, alignItems: 'center', justifyContent: 'center', padding: 24, borderRadius: 12, backgroundColor: '#e8eef5', borderWidth: 1, borderColor: '#c3d0e0' },
        style as never,
      ]}
    >
      <Text style={{ fontSize: 15, fontWeight: '700', color: '#1f4e79', textAlign: 'center' }}>Map not available in the browser</Text>
      <Text style={{ fontSize: 13, color: '#4a5b6e', textAlign: 'center', marginTop: 6 }}>
        The interactive map uses the native Google/Apple Maps SDK, which has no web build. Open the app on Android or iOS to see hotspots and offices plotted.
      </Text>
      <View style={{ display: 'none' }}>{children}</View>
    </View>
  );
}

// Child overlays render nothing on web; they are only meaningful inside a real MapView.
export const Marker = (_props: AnyProps) => null;
export const Circle = (_props: AnyProps) => null;
export const Polygon = (_props: AnyProps) => null;
export const Polyline = (_props: AnyProps) => null;
export const Callout = (_props: AnyProps) => null;
export const PROVIDER_GOOGLE = 'google';
export const PROVIDER_DEFAULT = undefined;
