from datetime import timedelta

from dateutil.relativedelta import relativedelta

BILLING_FREQUENCIES = [
    ('weekly', 'Weekly'),
    ('monthly', 'Monthly'),
    ('quarterly', 'Quarterly'),
    ('half_yearly', 'Half-Yearly'),
    ('yearly', 'Yearly'),
    ('custom', 'Custom'),
]

FREQUENCY_MONTHS = {
    'monthly': 1,
    'quarterly': 3,
    'half_yearly': 6,
    'yearly': 12,
}

# Booking states in which a site is really occupied by a customer.
BLOCKING_STATES = ('confirmed', 'active')


def compute_period_count(date_start, date_end, frequency):
    """Number of billing periods between two dates (end date inclusive).

    Whole periods count as 1 each; a trailing partial period is pro-rated by
    days. Returns 0.0 when the range is invalid. The ``custom`` frequency
    cannot be derived from dates and is handled by the caller.
    """
    if not date_start or not date_end or date_end < date_start:
        return 0.0
    end_exclusive = date_end + timedelta(days=1)
    if frequency == 'weekly':
        return round((end_exclusive - date_start).days / 7.0, 2)
    months = FREQUENCY_MONTHS.get(frequency)
    if not months:
        return 0.0
    month_gap = ((end_exclusive.year - date_start.year) * 12
                 + end_exclusive.month - date_start.month)
    full = max(month_gap // months - 1, 0)
    while date_start + relativedelta(months=months * (full + 1)) <= end_exclusive:
        full += 1
    cursor = date_start + relativedelta(months=months * full)
    remainder = (end_exclusive - cursor).days
    if remainder:
        period_end = date_start + relativedelta(months=months * (full + 1))
        return round(full + remainder / float((period_end - cursor).days), 2)
    return float(full)


def format_range(env, date_start, date_end):
    from odoo.tools.misc import format_date
    return f"{format_date(env, date_start)} - {format_date(env, date_end)}"


def drop_blank_import_values(env, vals, field_names):
    """Let blank cells of an imported file fall back to the computed default.

    The importer sends ``False`` / empty commands for empty cells, which would
    otherwise overwrite computed values (price, periods, taxes...).
    """
    if not env.context.get('import_file'):
        return vals
    for name in field_names:
        value = vals.get(name)
        blank_commands = isinstance(value, (list, tuple)) and all(
            command[0] == 5 or (command[0] == 6 and not command[2]) for command in value)
        if name in vals and (value is False or blank_commands):
            del vals[name]
    return vals
