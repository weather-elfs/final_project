export interface AlertPrinciple {
  title: string;
  description: string;
}

export interface AlertRule {
  id: string;
  missionType: string;
  triggerThreshold: string;
  clearThreshold: string;
  confirmationDuration: string;
  missingDataAction: string;
}

export interface DecisionRecord {
  id: string;
  occurredAt: string;
  status: 'ALERT' | 'UNAVAILABLE' | 'ERROR';
  mission: string;
  reason: string;
}

export interface AlertOperationsData {
  principles: AlertPrinciple[];
  rules: AlertRule[];
  decisions: DecisionRecord[];
}
