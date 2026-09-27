import { test, expect } from '@playwright/test';
import { interpolatePosition, movementDuration, validCoordinate } from '../src/telemetryMotion';

test('projection follows Mercator and takes the short path across the date line', () => {
  const middle = interpolatePosition([0, 0], [0, 60], .5);
  expect(middle[1]).toBeCloseTo(35.26438968, 6);
  expect(interpolatePosition([179, 0], [-179, 0], .5)[0]).toBe(180);
  expect(interpolatePosition([-179, 0], [179, 0], .5)[0]).toBe(-180);
  expect(interpolatePosition([0, 90], [0, 90], .5)[1]).toBeCloseTo(85.05112878);
});

test('invalid coordinates cannot reach the map', () => {
  expect(validCoordinate([37.6, 55.7])).toBe(true);
  for (const point of [[NaN, 0], [0, Infinity], [181, 0], [0, 91]]) {
    expect(validCoordinate(point as [number, number])).toBe(false);
  }
});

test('motion respects event time, replay speed, outages and reduced motion', () => {
  expect(movementDuration(100, 110, 60, true)).toBeCloseTo(1000 / 6);
  expect(movementDuration(100, 110, 1, true)).toBe(900);
  for (const previous of [undefined, 110, 120, 0]) {
    expect(movementDuration(previous, 110, 1, true)).toBe(0);
  }
  expect(movementDuration(100, 110, 1, false)).toBe(0);
});
