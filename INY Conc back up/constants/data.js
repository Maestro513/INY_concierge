export const SAMPLE_MEMBER = {
  firstName: 'Dorothy', lastName: 'Johnson', carrier: 'UHC',
  planName: 'AARP Medicare Advantage (PPO)', planId: 'H0028-007',
};
export const SAMPLE_BENEFITS = [
  { label: 'PCP Visit', value: '$0', icon: '🩺' },
  { label: 'Specialist', value: '$30', icon: '👨‍⚕️' },
  { label: 'Drug Deductible', value: '$0', icon: '💊' },
  { label: 'Max Out-of-Pocket', value: '$3,900', icon: '🛡️' },
];
export const QUICK_QUESTIONS = [
  "What's my specialist copay?", 'Is Eliquis covered?', 'Do I have dental?',
];
export const SAMPLE_ANSWERS = {
  "What's my specialist copay?": 'Your specialist copay is $30 per visit with an in-network provider. Out-of-network visits are $70.',
  'Is Eliquis covered?': 'Yes! Eliquis is on your formulary at Tier 3 (Preferred Brand). Your copay is $47 for a 30-day supply at a preferred retail pharmacy.',
  'Do I have dental?': 'Yes! Your plan includes preventive dental — oral exams and cleanings at $0 copay, up to 2 per year. Comprehensive dental has a $1,500 annual max.',
};
export const SAMPLE_SOB = {
  medical: [
    { label: 'Inpatient Hospital', value: '$325/day (days 1-5)' },
    { label: 'Outpatient Surgery', value: '$250 copay' },
    { label: 'Emergency Room', value: '$90 copay' },
    { label: 'Urgent Care', value: '$40 copay' },
  ],
  drugs: [
    { label: 'Tier 1 (Preferred Generic)', value: '$0' },
    { label: 'Tier 2 (Generic)', value: '$12' },
    { label: 'Tier 3 (Preferred Brand)', value: '$47' },
    { label: 'Tier 4 (Non-Preferred)', value: '$100' },
  ],
};
export const CALL_NUMBER = '8444632931';
