import { View } from 'react-native';
import { COLORS } from '../constants/theme';

/**
 * Pure-JS gradient background substitute.
 * Renders a colored top band that fades visually into the main bg.
 * No native module required (works in Expo Go + dev builds without rebuild).
 */
export default function GradientBg({ children, style, topColor, topHeight = '30%' }) {
  return (
    <View style={[{ flex: 1, backgroundColor: COLORS.bg }, style]}>
      <View
        style={{
          position: 'absolute', top: 0, left: 0, right: 0,
          height: topHeight,
          backgroundColor: topColor || COLORS.bgGradientTop,
        }}
      />
      {children}
    </View>
  );
}
