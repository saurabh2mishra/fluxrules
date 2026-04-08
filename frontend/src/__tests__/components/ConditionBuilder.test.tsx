import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ConditionBuilder } from '../../components/rules/ConditionBuilder';
import type { ConditionGroup } from '../../types/rule';


const baseTree: ConditionGroup = {
    type: 'group',
    op: 'AND',
    children: [
        { type: 'condition', field: 'is_active', op: '==', value: true },
    ],
};

describe('ConditionBuilder boolean guardrails', () => {
    it('shows boolean-string warning when condition value is string-like boolean', () => {
        const tree: ConditionGroup = {
            ...baseTree,
            children: [{ type: 'condition', field: 'is_active', op: '==', value: 'TRUE' }],
        };

        render(<ConditionBuilder value={tree} onChange={() => undefined} />);

        expect(
            screen.getByText(/Boolean-like string detected/i),
        ).toBeInTheDocument();
    });

    it('does not show warning when value is actual boolean', () => {
        render(<ConditionBuilder value={baseTree} onChange={() => undefined} />);

        expect(
            screen.queryByText(/Boolean-like string detected/i),
        ).not.toBeInTheDocument();
    });
});
