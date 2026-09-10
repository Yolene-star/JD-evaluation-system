import { describe, expect, it } from 'vitest'
import { activeStage } from './StageRail'
describe('stage rail state mapping', () => { it('keeps analysis active before confirmation', () => { expect(activeStage('REVIEWING')).toBe(1) }); it('moves to confirmation after freeze', () => { expect(activeStage('CONFIRMED')).toBe(2) }) })
