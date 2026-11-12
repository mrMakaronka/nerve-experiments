# superhero database: schema reference

SQLite. Generated from the warehouse on 2026-11-10.

## alignment

```sql
CREATE TABLE alignment
(
    id        INTEGER not null
            primary key,
    alignment TEXT default NULL
)
```

- `id`: the unique identifier of the alignment
- `alignment`: the alignment of the superhero (commonsense evidence: Alignment refers to a character's moral and ethical stance and can be used to describe the overall attitude or behavior of a superhero. So)

## attribute

```sql
CREATE TABLE attribute
(
    id             INTEGER not null
            primary key,
    attribute_name TEXT default NULL
)
```

- `id`: the unique identifier of the attribute
- `attribute_name`: the attribute (commonsense evidence: A superhero's attribute is a characteristic or quality that defines who they are and what they are capable of. This could be a physical tr)

## colour

```sql
CREATE TABLE colour
(
    id     INTEGER not null
            primary key,
    colour TEXT default NULL
)
```

- `id`: the unique identifier of the color
- `colour`: the color of the superhero's skin/eye/hair/etc

## gender

```sql
CREATE TABLE gender
(
    id     INTEGER not null
            primary key,
    gender TEXT default NULL
)
```

- `id`: the unique identifier of the gender
- `gender`: the gender of the superhero

## hero_attribute

```sql
CREATE TABLE hero_attribute
(
    hero_id         INTEGER default NULL,
    attribute_id    INTEGER default NULL,
    attribute_value INTEGER default NULL,
    foreign key (attribute_id) references attribute(id),
    foreign key (hero_id) references superhero(id)
)
```

- `hero_id`: the id of the hero Maps to superhero(id)
- `attribute_id`: the id of the attribute Maps to attribute(id)
- `attribute_value`: the attribute value (commonsense evidence: If a superhero has a higher attribute value on a particular attribute, it means that they are more skilled or powerful in that area compar)

## hero_power

```sql
CREATE TABLE hero_power
(
    hero_id  INTEGER default NULL,
    power_id INTEGER default NULL,
    foreign key (hero_id) references superhero(id),
    foreign key (power_id) references superpower(id)
)
```

- `hero_id`: the id of the hero Maps to superhero(id)
- `power_id`: the id of the power Maps to superpower(id) (commonsense evidence: In general, a superhero's attributes provide the foundation for their abilities and help to define who they are, while their powers are th)

## publisher

```sql
CREATE TABLE publisher
(
    id             INTEGER not null
            primary key,
    publisher_name TEXT default NULL
)
```

- `id`: the unique identifier of the publisher
- `publisher_name`: the name of the publisher

## race

```sql
CREATE TABLE race
(
    id   INTEGER not null
            primary key,
    race TEXT default NULL
)
```

- `id`: the unique identifier of the race
- `race`: the race of the superhero (commonsense evidence: In the context of superheroes, a superhero's race would refer to the particular group of people that the superhero belongs to base on thes)

## superhero

```sql
CREATE TABLE superhero
(
    id             INTEGER not null
            primary key,
    superhero_name TEXT default NULL,
    full_name      TEXT default NULL,
    gender_id      INTEGER          default NULL,
    eye_colour_id  INTEGER          default NULL,
    hair_colour_id INTEGER          default NULL,
    skin_colour_id INTEGER          default NULL,
    race_id        INTEGER          default NULL,
    publisher_id   INTEGER          default NULL,
    alignment_id   INTEGER          default NULL,
    height_cm      INTEGER          default NULL,
    weight_kg      INTEGER          default NULL,
    foreign key (alignment_id) references alignment(id),
    foreign key (eye_colour_id) references colour(id),
    foreign key (gender_id) references gender(id),
    foreign key (hair_colour_id) references colour(id),
    foreign key (publisher_id) references publisher(id),
    foreign key (race_id) references race(id),
    foreign key (skin_colour_id) references colour(id)
)
```

- `id`: the unique identifier of the superhero
- `superhero_name`: the name of the superhero
- `full_name`: the full name of the superhero (commonsense evidence: The full name of a person typically consists of their given name, also known as their first name or personal name, and their surname, also)
- `gender_id`: the id of the superhero's gender
- `eye_colour_id`: the id of the superhero's eye color
- `hair_colour_id`: the id of the superhero's hair color
- `skin_colour_id`: the id of the superhero's skin color
- `race_id`: the id of the superhero's race
- `publisher_id`: the id of the publisher
- `alignment_id`: the id of the superhero's alignment
- `height_cm`: the height of the superhero (commonsense evidence: The unit of height is centimeter. If the height_cm is NULL or 0, it means the height of the superhero is missing.)
- `weight_kg`: the weight of the superhero (commonsense evidence: The unit of weight is kilogram. If the weight_kg is NULL or 0, it means the weight of the superhero is missing.)

## superpower

```sql
CREATE TABLE superpower
(
    id         INTEGER not null
            primary key,
    power_name TEXT default NULL
)
```

- `id`: the unique identifier of the superpower
- `power_name`: the superpower name
