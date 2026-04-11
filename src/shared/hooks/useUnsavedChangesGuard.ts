import { useEffect } from 'react';
import { useBlocker } from 'react-router-dom';

const DEFAULT_MESSAGE = 'You have unsaved changes. Leave anyway?';

export function useUnsavedChangesGuard(isDirty: boolean, message = DEFAULT_MESSAGE) {
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    return isDirty && currentLocation.pathname !== nextLocation.pathname;
  });

  useEffect(() => {
    if (blocker.state !== 'blocked') {
      return;
    }

    if (window.confirm(message)) {
      blocker.proceed();
      return;
    }

    blocker.reset();
  }, [blocker, message]);

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!isDirty) {
        return;
      }

      event.preventDefault();
      event.returnValue = message;
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [isDirty, message]);
}
