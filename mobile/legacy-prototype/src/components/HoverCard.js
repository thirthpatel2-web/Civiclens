// CivicLens - Butter-Smooth Interactive Hover & Elevate Card Component

import React, { useState } from 'react';
import { TouchableOpacity, Platform, StyleSheet } from 'react-native';
import { useApp } from '../context/AppContext';
import { RADIUS } from '../constants/theme';

export default function HoverCard({
  children,
  onPress,
  style,
  glowColor,
  hoverTranslateY = -4,
  activeOpacity = 0.9,
  disabled = false,
}) {
  const { theme } = useApp();
  const [isHovered, setIsHovered] = useState(false);

  const activeGlow = glowColor || theme.primary;

  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={disabled}
      activeOpacity={activeOpacity}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={[
        styles.baseCard,
        style,
        {
          backgroundColor: theme.card,
          borderColor: isHovered ? activeGlow : theme.cardBorder,
          borderWidth: 1.5,
          transform: isHovered
            ? [{ translateY: hoverTranslateY }]
            : [{ translateY: 0 }],
          cursor: Platform.OS === 'web' ? 'pointer' : 'default',
          ...(Platform.OS === 'web'
            ? {
                transition: 'transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease, box-shadow 0.3s cubic-bezier(0.16, 1, 0.3, 1), background-color 0.25s ease',
                boxShadow: isHovered
                  ? `0 10px 22px -3px ${activeGlow}40, 0 4px 8px -2px ${activeGlow}25`
                  : '0 2px 6px rgba(0, 0, 0, 0.15)',
                outline: 'none',
                boxSizing: 'border-box',
              }
            : {
                shadowColor: isHovered ? activeGlow : '#000',
                shadowOpacity: isHovered ? 0.3 : 0.08,
                shadowRadius: isHovered ? 10 : 4,
                shadowOffset: { width: 0, height: isHovered ? 4 : 2 },
                elevation: isHovered ? 6 : 2,
              }),
        },
      ]}
    >
      {typeof children === 'function' ? children({ isHovered }) : children}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  baseCard: {
    borderRadius: RADIUS.md,
    padding: 12,
    borderWidth: 1.5,
    overflow: 'visible',
  },
});
