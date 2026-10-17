import { SkeletonBlock } from '../shared/ui/StateViews';
import { DemoBanner } from './DemoBanner';

/** Wird beim ersten Laden einer lazy Route gezeigt; der Demo-Hinweis bleibt dabei an derselben Stelle. */
export function HydrateFallback() {
  return (
    <>
      <DemoBanner />
      <div className="mx-auto w-full max-w-6xl px-4 py-6">
        <SkeletonBlock lines={4} />
      </div>
    </>
  );
}
