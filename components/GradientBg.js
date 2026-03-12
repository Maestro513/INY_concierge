import { View } from 'react-native';
import { COLORS } from '../constants/theme';

/**
 * Pure-JS gradient background substitute.
 * Stacks multiple translucent bands to approximate a top-to-bottom fade.
 * No native module required (works in Expo Go + dev builds without rebuild).
 */
export default function GradientBg({ children, style, topColor, _topHeight = '35%' }) {
  const top = topColor || COLORS.bgGradientTop;
  return (
    <View style={[{ flex: 1, backgroundColor: COLORS.bg }, style]}>
      {/* Band 1 – full strength at very top */}
      <View
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: '12%',
          backgroundColor: top,
          opacity: 0.7,
        }}
      />
      {/* Band 2 – fading */}
      <View
        style={{
          position: 'absolute',
          top: '10%',
          left: 0,
          right: 0,
          height: '12%',
          backgroundColor: top,
          opacity: 0.45,
        }}
      />
      {/* Band 3 – subtle */}
      <View
        style={{
          position: 'absolute',
          top: '20%',
          left: 0,
          right: 0,
          height: '12%',
          backgroundColor: top,
          opacity: 0.2,
        }}
      />
      {/* Band 4 – barely visible */}
      <View
        style={{
          position: 'absolute',
          top: '28%',
          left: 0,
          right: 0,
          height: '10%',
          backgroundColor: top,
          opacity: 0.08,
        }}
      />
      {children}
    </View>
  );
}
