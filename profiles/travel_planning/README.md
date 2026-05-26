# Travel Planning Memory Profile

## Overview

The Travel Planning Memory profile captures structured travel information to provide personalized recommendations and assistance throughout the trip planning process.

## Use Cases

- **Trip Planning**: Extract and store destination preferences, dates, budget, and traveler details
- **Booking Management**: Track confirmed reservations for flights, hotels, and activities
- **Personalization**: Remember preferences for accommodation types, activity styles, and dietary needs
- **Constraint Tracking**: Ensure must-see attractions, accessibility needs, and restrictions are respected

## Schema Overview

### Required Fields
- `destination` - Primary travel destination (city, country, or region)

### Optional Fields

#### Dates
| Field | Type | Description |
|-------|------|-------------|
| `start_date` | date | Trip start date (YYYY-MM-DD) |
| `end_date` | date | Trip end date (YYYY-MM-DD) |
| `duration_days` | integer | Total number of days |
| `flexibility` | enum | fixed, flexible_1_3_days, flexible_week, flexible_month, open |

#### Travelers
| Field | Type | Description |
|-------|------|-------------|
| `count` | integer | Number of travelers |
| `composition` | array | solo, partner, family_with_children, friends, group, seniors, pets |
| `ages` | object | adults, children, infants counts |

#### Budget
| Field | Type | Description |
|-------|------|-------------|
| `total_budget` | number | Total trip budget |
| `currency` | string | Currency code (USD, EUR, etc.) |
| `budget_tier` | enum | budget, mid_range, luxury, ultra_luxury |
| `per_person_max` | number | Maximum per person |

#### Preferences
| Field | Type | Description |
|-------|------|-------------|
| `accommodation_type` | array | hotel, resort, airbnb, hostel, boutique, camping, glamping, all_inclusive |
| `room_preferences` | array | Specific room requirements |
| `activity_style` | array | relaxing, adventure, cultural, foodie, nightlife, nature, shopping, wellness |
| `pace` | enum | packed, moderate, relaxed, very_relaxed |
| `dietary_restrictions` | array | Dietary requirements |
| `accessibility_needs` | array | Accessibility accommodations |

#### Purpose
| Field | Type | Description |
|-------|------|-------------|
| `primary` | enum | vacation, business, bleisure, honeymoon, anniversary, family_reunion, celebration, adventure, wellness, education |
| `secondary` | array | Additional purposes |
| `special_occasion` | string | Description if applicable |

#### Constraints
| Field | Type | Description |
|-------|------|-------------|
| `must_visit` | array | Required attractions/locations |
| `must_avoid` | array | Places/activities to avoid |
| `transportation_preferences` | array | flight, train, car_rental, public_transit, walking, cruise, private_driver |
| `visa_requirements` | object | Visa needs and status |
| `health_requirements` | array | Vaccinations, medications |
| `time_constraints` | string | Time limitations |

#### Booked Items
Array of confirmed bookings with type, name, confirmation number, date, and cost.

## Capture Behavior

### Default Settings
- **Capture Stage**: Post-response async (to avoid latency)
- **Trigger**: Conversation end
- **Scope**: Conversation (can be changed to user-scoped for persistent preferences)
- **Indexing**: FTS only (for text search)
- **Retrieval**: Injected into prompts

### Confidence Levels
The extraction agent assigns confidence based on how explicitly the information was stated:
- **HIGH**: User explicitly stated
- **MEDIUM**: Strongly implied
- **LOW**: Weakly inferred

## Usage Examples

### Creating a Travel Memory

When a user mentions travel plans, the memory agent extracts:

```
User: "I'm going to Japan for 2 weeks in April with my partner"
→ Extracts: destination=Japan, dates.duration_days=14, travelers.composition=[partner]

User: "Budget is around $5000, we're staying at boutique hotels"
→ Extracts: budget.total_budget=5000, budget.currency=USD, preferences.accommodation_type=[boutique]
```

### Retrieving Travel Memories

Memories can be retrieved by:
- Destination (e.g., all Japan trips)
- Date range (e.g., upcoming trips)
- Traveler composition (e.g., family trips)
- Purpose (e.g., honeymoons)

### Memory Lifecycle

1. **Planning Phase**: Memory created with available details
2. **Booking Phase**: `booked_items` populated as reservations are made
3. **Pre-trip Phase**: Memory retrieved for final recommendations
4. **Post-trip Phase**: Memory archived or updated with trip notes

## Integration Tips

### With Travel Agents
Enable this profile on travel planning agents to remember user preferences across sessions.

### Scope Recommendations
- **Conversation scope**: For one-off trip planning
- **User scope**: For persistent travel preferences (frequent travelers)
- **Global scope**: For shared destination knowledge

### Customization
Modify the schema to add domain-specific fields:
- Cruise-specific fields (ship, cabin type, ports)
- Business travel fields (company policy, loyalty programs)
- Adventure travel fields (gear requirements, fitness level)

## File Structure

```
travel_planning/
├── profile.json          # Schema and configuration
├── capture_prompt.txt    # Extraction instructions for the memory agent
├── example_records.json  # Sample memory records
└── README.md            # This documentation
```

## Version History

- **1.0.0** - Initial profile with core travel planning fields
