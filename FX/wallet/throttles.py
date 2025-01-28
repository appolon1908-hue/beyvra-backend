from rest_framework.throttling import UserRateThrottle

class DepositRateThrottle(UserRateThrottle):
    scope = 'deposit'

class WithdrawalRateThrottle(UserRateThrottle):
    scope = 'withdrawal'

class TransferRateThrottle(UserRateThrottle):
    scope = 'transfer'
