/**
 * Tuned wordmark mark (web logo_transparent_bg_noshadow.svg paths).
 */
import Svg, { Path } from 'react-native-svg';
import { brand } from '../theme/tokens';

type Props = {
  size?: number;
};

export function BrandLogo({ size = 28 }: Props) {
  return (
    <Svg width={size} height={size} viewBox="0 0 530 530" fill="none">
      <Path
        d="M162.5 50V250H87.5V50H0V0H250V50H162.5Z"
        fill={brand.fuchsia}
      />
      <Path
        d="M250 280V530H172.131L73.771 380V530H0V280H77.869L176.229 430V280H250Z"
        fill={brand.fuchsia}
      />
      <Path
        d="M458.571 179.577V0H530V179.577C530 204.225 523.717 222.124 511.151 233.275C498.585 244.425 478.413 250 450.635 250H359.365C331.587 250 311.415 244.425 298.849 233.275C286.283 222.124 280 204.225 280 179.577V0H351.429V179.577C351.429 193.662 359.365 200.704 375.238 200.704H434.762C450.635 200.704 458.571 193.662 458.571 179.577Z"
        fill={brand.fuchsia}
      />
      <Path
        d="M530 480V530H280V280H530V330H361.081V378.214H493.964V428.214H361.081V480H530Z"
        fill={brand.fuchsia}
      />
    </Svg>
  );
}
