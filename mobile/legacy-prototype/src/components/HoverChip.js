// CivicLens - Butter-Smooth Interactive Hover Chip Component

import React, { useState } from 'react';
import { TouchableOpacity, Platform, StyleSheet } from 'react-native';
import { useApp } from '../context/AppContext';
import { RADIUS } from '../constants/theme';

export default function HoverChip({
  children,
  onPress,
  style,
  isSelected = false,
  activeColor,
}) {
  const { theme } = useApp();
  const [isHovered, setIsHovered] = useState(false);

  const chipColor = activeColor || theme.primary;

  return (
    <TouchableOpacity
      onPress={onPress}
      activeOpacity={0.85}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={[
        styles.baseChip,
        style,
        {
          backgroundColor: isSelected
            ? chipColor
            : isHovered
            ? chipColor + '20'
            : theme.card,
          borderColor: isSelected || isHovered ? chipColor : theme.cardBorder,
          borderWidth: 1.2,
          transform: isHovered ? [{ translateY: -2 }] : [{ translateY: 0 }],
          cursor: Platform.OS === 'web' ? 'pointer' : 'default',
          ...(Platform.OS === 'web'
            ? {
                transition: 'transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.2s ease, background-color 0.2s ease, box-shadow 0.25s ease',
                boxShadow: isHovered
                  ? `0 4px 12px ${chipColor}30`
                  : isSelected
                  ? `0 2px 6px ${chipColor}25`
                  : 'none',
                outline: 'none',
              }
            : {
                shadowColor: chipColor,
                shadowOpacity: isHovered ? 0.25 : isSelected ? 0.2 : 0,
                shadowRadius: isHovered ? 6 : 3,
                elevation: isHovered ? 3 : isSelected ? 2 : 0,
              }),
        },
      ]}
    >
      {typeof children === 'function' ? children({ isHovered, isSelected }) : children}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  baseChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: RADIUS.full,
    borderWidth: 1.2,
    marginRight: 8,
    overflow: 'visible',
  },
});
