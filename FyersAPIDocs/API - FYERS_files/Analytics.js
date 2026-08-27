function analytics(eventName, eventCategory, eventLabel, analyticsProvider) {
  if (!analyticsProvider) {
    analyticsProvider = 'gtag';
  }

  switch (analyticsProvider) {
    case 'gtag':
      gtag('event', eventName, {
        'event_category': eventCategory,
        'event_label': eventLabel
      });
      break;
    case 'other_analytics_provider':
      // Add code for another analytics provider here
      break;
    default:
      console.error('Unknown analytics provider');
  }
}